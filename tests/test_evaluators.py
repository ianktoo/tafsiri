from tafsiri.evaluators.backtranslation import BackTranslationEvaluator, similarity
from tafsiri.evaluators.confidence import ConfidenceEvaluator
from tafsiri.evaluators.llm_judge import LLMJudgeEvaluator, _parse_scores
from tafsiri.schema import SourceRecord, Translation

from conftest import EchoBackTranslator, FakeChatModel


# --- confidence ---------------------------------------------------------
def test_confidence_passes_through(source, ok_translation):
    sig = ConfidenceEvaluator().evaluate(source, ok_translation)
    assert sig.name == "confidence"
    assert sig.score == 0.8


def test_confidence_none_when_missing(source):
    tr = Translation("English", "Swahili", text="x", confidence=None, ok=True)
    assert ConfidenceEvaluator().evaluate(source, tr).score is None


def test_confidence_clamped(source):
    tr = Translation("English", "Swahili", text="x", confidence=1.5, ok=True)
    assert ConfidenceEvaluator().evaluate(source, tr).score == 1.0


# --- back-translation ---------------------------------------------------
def test_similarity_bounds():
    assert similarity("a b c", "a b c") == 1.0
    assert similarity("a b c", "x y z") < 0.5
    assert similarity("", "") == 1.0
    assert similarity("a", "") == 0.0


def test_backtranslation_perfect_roundtrip(source):
    ev = BackTranslationEvaluator(EchoBackTranslator())
    tr = Translation("English", "Swahili", text="<<hello world>>",
                     confidence=0.9, ok=True)
    sig = ev.evaluate(source, tr)
    # echo restores original text exactly -> similarity 1.0
    assert sig.score == 1.0
    assert sig.detail["back_translation"] == "hello world"


# --- llm judge ----------------------------------------------------------
def test_parse_scores_extracts_json():
    assert _parse_scores('noise {"adequacy": 5, "fluency": 4} tail') == {
        "adequacy": 5, "fluency": 4}
    assert _parse_scores("no json here") is None


def test_llm_judge_normalizes_mean(source, ok_translation):
    model = FakeChatModel('{"adequacy": 5, "fluency": 3, "reason": "ok"}')
    sig = LLMJudgeEvaluator(model).evaluate(source, ok_translation)
    # mean = 4 -> (4-1)/4 = 0.75
    assert sig.score == 0.75
    assert sig.detail["adequacy"] == 5


def test_llm_judge_unparseable_output_is_none(source, ok_translation):
    sig = LLMJudgeEvaluator(FakeChatModel("garbage")).evaluate(source, ok_translation)
    assert sig.score is None


def test_llm_judge_handles_invoke_exception(source, ok_translation):
    class Boom:
        def invoke(self, _):
            raise RuntimeError("provider down")

    sig = LLMJudgeEvaluator(Boom()).evaluate(source, ok_translation)
    assert sig.score is None
    assert "provider down" in sig.detail["error"]
