"""Confidence evaluator — trusts the provider's own confidence score.

Cheapest signal: no extra API calls. Just surfaces ``Translation.confidence``
(assumed already 0..1) as a normalized signal.
"""

from __future__ import annotations

from tafsiri.schema import EvalSignal, SourceRecord, Translation


class ConfidenceEvaluator:
    name = "confidence"

    def evaluate(self, source: SourceRecord, translation: Translation) -> EvalSignal:
        if not translation.ok or translation.confidence is None:
            return EvalSignal(self.name, None,
                              {"reason": "no confidence available"})
        score = max(0.0, min(1.0, float(translation.confidence)))
        return EvalSignal(self.name, score, {"raw_confidence": translation.confidence})
