from tafsiri.schema import EvalResult, EvalSignal, SourceRecord, TranslatedRecord, Translation
from tafsiri.serialize import flatten_record, record_from_row


def _record():
    src = SourceRecord(id="s1", text="hello", src_lang="English",
                       meta={"speaker": "first_responder", "category": "medical"})
    tr = Translation("English", "Swahili", text="habari", confidence=0.8,
                     model="babel", ok=True)
    ev = EvalResult(signals=[EvalSignal("confidence", 0.8, {"raw_confidence": 0.8})],
                    aggregate_score=0.8, rating="marginal")
    return TranslatedRecord(source=src, translation=tr, evaluation=ev)


def test_flatten_then_reconstruct_roundtrip():
    rec = _record()
    rebuilt = record_from_row(flatten_record(rec))

    assert rebuilt.source.id == "s1"
    assert rebuilt.source.text == "hello"
    assert rebuilt.source.meta["speaker"] == "first_responder"
    assert rebuilt.translation.tgt_lang == "Swahili"
    assert rebuilt.translation.text == "habari"
    assert rebuilt.translation.confidence == 0.8
    assert rebuilt.translation.ok is True
    assert rebuilt.evaluation.rating == "marginal"
    assert rebuilt.evaluation.aggregate_score == 0.8
    assert rebuilt.evaluation.signal("confidence").score == 0.8


def test_reconstruct_failed_record():
    src = SourceRecord(id="s2", text="bye", src_lang="English")
    tr = Translation("English", "Yoruba", ok=False, error="HTTP 429")
    rec = TranslatedRecord(source=src, translation=tr, evaluation=EvalResult(rating="no_score"))
    rebuilt = record_from_row(flatten_record(rec))
    assert rebuilt.translation.ok is False
    assert rebuilt.translation.error == "HTTP 429"
    assert rebuilt.evaluation.rating == "no_score"
