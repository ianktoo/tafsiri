"""Evaluation strategies (the *quality* concern).

Each evaluator turns a (source, translation) pair into a single normalized
EvalSignal in 0..1. They are independent and composable — the pipeline runs
whichever set you pass it, and scoring combines their signals.
"""

from tafsiri.evaluators.backtranslation import BackTranslationEvaluator
from tafsiri.evaluators.base import Evaluator
from tafsiri.evaluators.confidence import ConfidenceEvaluator
from tafsiri.evaluators.llm_judge import LLMJudgeEvaluator, make_chat_model

__all__ = [
    "Evaluator",
    "ConfidenceEvaluator",
    "BackTranslationEvaluator",
    "LLMJudgeEvaluator",
    "make_chat_model",
]
