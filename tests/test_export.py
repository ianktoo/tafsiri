import json

from tafsiri.export import (
    build_report,
    write_chat_jsonl,
    write_csv,
    write_pairs_jsonl,
)
from tafsiri.schema import EvalResult, SourceRecord, TranslatedRecord, Translation


def _rec(rid, rating, score, ok=True, text="trans", speaker="affected_party"):
    src = SourceRecord(id=rid, text="src text", src_lang="English",
                       meta={"speaker": speaker, "category": "medical"})
    tr = Translation("English", "Swahili", text=text if ok else None,
                     confidence=score, model="babel", ok=ok,
                     error=None if ok else "fail")
    ev = EvalResult(aggregate_score=score, rating=rating)
    return TranslatedRecord(source=src, translation=tr, evaluation=ev)


def _records():
    return [
        _rec("good1", "good", 0.9),
        _rec("marg1", "marginal", 0.75),
        _rec("risk1", "risky", 0.4),
        _rec("fail1", "no_score", None, ok=False),
    ]


def test_chat_export_filters_by_min_rating(tmp_path):
    p = tmp_path / "chat.jsonl"
    n = write_chat_jsonl(_records(), p, min_rating="marginal")
    lines = [json.loads(l) for l in p.read_text(encoding="utf-8").splitlines()]
    assert n == 2  # good + marginal only
    first = lines[0]
    assert [m["role"] for m in first["messages"]] == ["system", "user", "assistant"]
    assert "Swahili" in first["messages"][0]["content"]
    assert first["meta"]["speaker"] == "affected_party"


def test_chat_export_good_only(tmp_path):
    p = tmp_path / "chat.jsonl"
    n = write_chat_jsonl(_records(), p, min_rating="good")
    assert n == 1


def test_pairs_export_shape(tmp_path):
    p = tmp_path / "pairs.jsonl"
    write_pairs_jsonl(_records(), p, min_rating="marginal")
    rows = [json.loads(l) for l in p.read_text(encoding="utf-8").splitlines()]
    assert rows[0]["input"] == "src text"
    assert rows[0]["output"] == "trans"
    assert rows[0]["tgt_lang"] == "Swahili"


def test_csv_includes_all_rows(tmp_path):
    p = tmp_path / "out.csv"
    n = write_csv(_records(), p)
    assert n == 4
    header = p.read_text(encoding="utf-8").splitlines()[0]
    assert "rating" in header and "translation" in header


def test_report_counts_and_verdict():
    report = build_report(_records())
    assert report["total"] == 4
    assert report["ok"] == 3
    assert report["rating_counts"]["good"] == 1
    assert report["rating_counts"]["risky"] == 1
    # a risky present -> NOT A FIT verdict
    assert "NOT A FIT" in report["verdict"]
    assert "Swahili" in report["by_language"]
    assert "affected_party" in report["by_speaker"]
