"""Back-translation evaluator — round-trip the translation back to the source
language and measure how close it lands to the original.

A round-trip that drifts far from the source is a strong smell that meaning was
lost. Similarity uses difflib (stdlib) on normalized tokens, so this needs no
extra dependency beyond a Translator to do the reverse pass.
"""

from __future__ import annotations

import re
from difflib import SequenceMatcher

from tafsiri.providers.base import Translator
from tafsiri.schema import EvalSignal, SourceRecord, Translation

_WORD = re.compile(r"\w+", re.UNICODE)


def _normalize(text: str) -> list[str]:
    return _WORD.findall(text.lower())


def similarity(a: str, b: str) -> float:
    """0..1 token-sequence similarity (order-sensitive ratio)."""
    ta, tb = _normalize(a), _normalize(b)
    if not ta and not tb:
        return 1.0
    if not ta or not tb:
        return 0.0
    return SequenceMatcher(None, ta, tb).ratio()


class BackTranslationEvaluator:
    name = "back_translation"

    def __init__(self, translator: Translator):
        self.translator = translator

    def evaluate(self, source: SourceRecord, translation: Translation) -> EvalSignal:
        if not translation.ok or not translation.text:
            return EvalSignal(self.name, None, {"reason": "no translation to round-trip"})

        back = self.translator.translate(
            translation.text, translation.tgt_lang, translation.src_lang)
        if not back.ok or not back.text:
            return EvalSignal(self.name, None,
                              {"reason": "back-translation failed", "error": back.error})

        score = similarity(source.text, back.text)
        return EvalSignal(self.name, score, {
            "back_translation": back.text,
            "back_confidence": back.confidence,
        })
