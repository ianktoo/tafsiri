from tafsiri.schema import EvalResult, EvalSignal, SourceRecord, TranslatedRecord, Translation
from tafsiri.storage import SQLiteStore, Sink


def _record(rid="s1", tgt="Swahili", score=0.9, rating="good"):
    src = SourceRecord(id=rid, text="hello", src_lang="English",
                       meta={"speaker": "first_responder", "category": "medical"})
    tr = Translation("English", tgt, text="habari", confidence=score,
                     model="babel", ok=True)
    ev = EvalResult(signals=[EvalSignal("confidence", score)],
                    aggregate_score=score, rating=rating)
    return TranslatedRecord(source=src, translation=tr, evaluation=ev)


def test_sqlitestore_is_a_sink():
    assert isinstance(SQLiteStore(":memory:"), Sink)


def test_save_and_fetch_roundtrip():
    store = SQLiteStore(":memory:")
    store.start_run("r1", {"langs": ["Swahili"]})
    store.save_record("r1", _record())
    rows = store.fetch_records("r1")
    assert len(rows) == 1
    row = rows[0]
    assert row["source_id"] == "s1"
    assert row["translation"] == "habari"
    assert row["rating"] == "good"
    assert row["speaker"] == "first_responder"
    assert row["ok"] is True
    assert row["signals"][0]["name"] == "confidence"
    store.close()


def test_upsert_is_idempotent():
    store = SQLiteStore(":memory:")
    store.start_run("r1", {})
    store.save_record("r1", _record(score=0.5, rating="risky"))
    store.save_record("r1", _record(score=0.95, rating="good"))  # same key, updated
    rows = store.fetch_records("r1")
    assert len(rows) == 1  # not duplicated
    assert rows[0]["rating"] == "good"  # latest value won
    store.close()


def test_runs_and_summary_persist():
    store = SQLiteStore(":memory:")
    store.start_run("r1", {"x": 1}, created_at="2026-05-31T00:00:00")
    store.finish_run("r1", {"avg_score": 0.8, "verdict": "GOOD FIT"})
    runs = store.list_runs()
    assert len(runs) == 1
    assert runs[0]["run_id"] == "r1"
    import json
    assert json.loads(runs[0]["summary"])["verdict"] == "GOOD FIT"
    store.close()


def test_persistence_across_connections(tmp_path):
    db = tmp_path / "t.db"
    s1 = SQLiteStore(db)
    s1.start_run("r1", {})
    s1.save_record("r1", _record())
    s1.close()
    # reopen — data must still be there
    s2 = SQLiteStore(db)
    assert len(s2.fetch_records("r1")) == 1
    s2.close()
