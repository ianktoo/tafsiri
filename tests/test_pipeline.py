import pytest

from tafsiri.evaluators.backtranslation import BackTranslationEvaluator
from tafsiri.evaluators.confidence import ConfidenceEvaluator
from tafsiri.pipeline import RateLimitAbort, run_pipeline
from tafsiri.schema import SourceRecord, Translation

from conftest import EchoBackTranslator, FakeTranslator


class AlwaysFailTranslator:
    name = "always-fail"

    def __init__(self):
        self.calls = 0

    def translate(self, text, src_lang, tgt_lang):
        self.calls += 1
        return Translation(src_lang=src_lang, tgt_lang=tgt_lang, ok=False,
                           error="HTTP 429: Too many requests")


def _sources():
    return [
        SourceRecord(id="a", text="hello", src_lang="English", meta={"speaker": "x"}),
        SourceRecord(id="b", text="bye", src_lang="English"),
    ]


def test_pipeline_translates_every_source_x_lang():
    translator = FakeTranslator(confidence=0.9)
    records = run_pipeline(_sources(), ["Swahili", "Yoruba"], translator,
                           [ConfidenceEvaluator()])
    assert len(records) == 4  # 2 sources x 2 langs
    assert all(r.translation.ok for r in records)
    assert all(r.evaluation.rating == "good" for r in records)


def test_pipeline_streams_to_on_record_callback():
    seen = []
    translator = FakeTranslator()
    run_pipeline(_sources(), ["Swahili"], translator, [ConfidenceEvaluator()],
                 on_record=lambda rec: seen.append(rec.source.id))
    assert seen == ["a", "b"]


def test_pipeline_records_failed_translation_without_crashing():
    translator = FakeTranslator(fail_for={"bye"})
    records = run_pipeline(_sources(), ["Swahili"], translator, [ConfidenceEvaluator()])
    by_id = {r.source.id: r for r in records}
    assert by_id["a"].translation.ok
    assert not by_id["b"].translation.ok
    assert by_id["b"].evaluation.rating == "no_score"


def test_pipeline_with_backtranslation_evaluator():
    translator = EchoBackTranslator()
    records = run_pipeline([SourceRecord(id="a", text="hello", src_lang="English")],
                           ["Swahili"], translator,
                           [ConfidenceEvaluator(), BackTranslationEvaluator(translator)])
    rec = records[0]
    bt = rec.evaluation.signal("back_translation")
    assert bt is not None and bt.score == 1.0


def test_pipeline_skips_given_keys():
    translator = FakeTranslator()
    records = run_pipeline(_sources(), ["Swahili"], translator,
                           [ConfidenceEvaluator()], skip={("a", "Swahili")})
    ids = [(r.source.id, r.translation.tgt_lang) for r in records]
    assert ("a", "Swahili") not in ids
    assert ("b", "Swahili") in ids
    # the skipped source's text was never sent to the translator
    assert all(call[0] != "hello" for call in translator.calls)


def test_circuit_breaker_escalates_then_aborts():
    translator = AlwaysFailTranslator()
    sources = [SourceRecord(id=str(i), text="t") for i in range(50)]
    sleeps: list[float] = []
    with pytest.raises(RateLimitAbort) as ei:
        run_pipeline(sources, ["Swahili"], translator, [ConfidenceEvaluator()],
                     fail_threshold=3, max_cooldowns=2, cooldown_base=1.0,
                     sleep=lambda s: sleeps.append(s))
    # cooldown after 3 fails (1s), after 3 more (2s), then abort on the 3rd hit
    assert sleeps == [1.0, 2.0]
    assert len(ei.value.records) == 9  # 3 * 3 failures processed before abort
    assert "persistent failures" in ei.value.reason


def test_circuit_breaker_resets_on_recovery():
    # one failure then all successes -> never trips the breaker
    translator = FakeTranslator(fail_for={"bad"})
    sources = [SourceRecord(id="x", text="bad"),
               SourceRecord(id="y", text="good")]
    records = run_pipeline(sources, ["Swahili"], translator, [ConfidenceEvaluator()],
                           fail_threshold=2, max_cooldowns=1, cooldown_base=1.0,
                           sleep=lambda s: (_ for _ in ()).throw(AssertionError("should not sleep")))
    assert len(records) == 2
