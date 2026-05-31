"""Combine evaluator signals into one aggregate score and a fit rating.

Aggregate = weighted mean over the signals that produced a score (None signals
are skipped, and their weight is redistributed). Rating buckets the aggregate
against safety thresholds — for emergency/medical text the bar is deliberately
high.
"""

from __future__ import annotations

from dataclasses import dataclass

from tafsiri.schema import EvalResult, EvalSignal

# Default weights. Back-translation and the LLM judge are stronger evidence of
# preserved *meaning* than the provider's self-reported confidence.
DEFAULT_WEIGHTS = {
    "confidence": 1.0,
    "back_translation": 1.5,
    "llm_judge": 2.0,
}

GOOD = 0.85       # trustworthy enough to relay / keep for training as-is
MARGINAL = 0.70   # usable but flag for human review


@dataclass
class Scorer:
    weights: dict[str, float] | None = None
    good: float = GOOD
    marginal: float = MARGINAL

    def aggregate(self, signals: list[EvalSignal]) -> float | None:
        weights = self.weights or DEFAULT_WEIGHTS
        num = den = 0.0
        for s in signals:
            if s.score is None:
                continue
            w = weights.get(s.name, 1.0)
            num += w * s.score
            den += w
        return None if den == 0 else num / den

    def rate(self, score: float | None) -> str:
        if score is None:
            return "no_score"
        if score >= self.good:
            return "good"
        if score >= self.marginal:
            return "marginal"
        return "risky"

    def score(self, signals: list[EvalSignal]) -> EvalResult:
        agg = self.aggregate(signals)
        return EvalResult(signals=list(signals), aggregate_score=agg,
                          rating=self.rate(agg))
