"""Prompts for LLM-based translation engines."""

from __future__ import annotations

TRANSLATE_SYSTEM = (
    "You are a professional translator. Translate the user's text faithfully "
    "from the source language to the target language. Preserve meaning, names, "
    "numbers, and tone. Do NOT add explanations, notes, transliterations, or "
    "quotation marks. Respond with ONLY the translated text."
)


def build_translate_user(text: str, src_lang: str, tgt_lang: str) -> str:
    """Per-item translation prompt. Override via
    ``LLMTranslator(user_builder=...)`` for a different style."""
    return f"Translate from {src_lang} to {tgt_lang}:\n\n{text}"
