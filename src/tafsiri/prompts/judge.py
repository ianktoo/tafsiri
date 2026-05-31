"""Prompts for the LLM-as-judge evaluator."""

from __future__ import annotations

JUDGE_SYSTEM = (
    "You are a strict bilingual translation evaluator. Given a source sentence "
    "and its translation into a target language, rate the translation on two "
    "axes, each an integer from 1 (terrible) to 5 (perfect):\n"
    "  - adequacy: is the full meaning preserved, with nothing added or lost?\n"
    "  - fluency: is it natural, grammatical text in the target language?\n"
    "For safety-critical (emergency/medical/financial) text, penalize any change "
    "in meaning harshly. Respond with ONLY a compact JSON object: "
    '{"adequacy": <int>, "fluency": <int>, "reason": "<short>"}.'
)


def build_judge_user(source_text: str, src_lang: str, tgt_lang: str,
                     translation: str) -> str:
    """Build the per-item judge prompt. Override by passing your own callable
    with this signature to ``LLMJudgeEvaluator(user_builder=...)``."""
    return (
        f"Source language: {src_lang}\n"
        f"Target language: {tgt_lang}\n"
        f"Source: {source_text}\n"
        f"Translation: {translation}"
    )
