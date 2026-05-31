from tafsiri.evaluators.backtranslation import BackTranslationEvaluator
from tafsiri.evaluators.confidence import ConfidenceEvaluator
from tafsiri.pipeline import run_pipeline
from tafsiri.schema import SourceRecord

from conftest import EchoBackTranslator, FakeTranslator


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
