"""The Evaluator protocol — produce one normalized quality signal."""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from tafsiri.schema import EvalSignal, SourceRecord, Translation


@runtime_checkable
class Evaluator(Protocol):
    """Scores a translation. ``score`` in the returned signal is 0..1 (higher is
    better) or None when the evaluator can't judge this item. Evaluators must
    not raise on bad input — they degrade to a None score with a reason in
    ``detail``."""

    name: str

    def evaluate(self, source: SourceRecord, translation: Translation) -> EvalSignal:
        ...
