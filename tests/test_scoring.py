import pytest

from tafsiri.schema import EvalSignal
from tafsiri.scoring import Scorer


def test_aggregate_is_weighted_mean():
    scorer = Scorer(weights={"a": 1.0, "b": 3.0})
    signals = [EvalSignal("a", 0.4), EvalSignal("b", 0.8)]
    # (1*0.4 + 3*0.8) / 4 = 0.7
    assert scorer.aggregate(signals) == pytest.approx(0.7)


def test_aggregate_skips_none_and_redistributes_weight():
    scorer = Scorer(weights={"a": 1.0, "b": 1.0})
    signals = [EvalSignal("a", 0.6), EvalSignal("b", None)]
    assert scorer.aggregate(signals) == 0.6


def test_aggregate_all_none_returns_none():
    scorer = Scorer()
    assert scorer.aggregate([EvalSignal("a", None)]) is None


def test_rating_thresholds():
    scorer = Scorer(good=0.85, marginal=0.70)
    assert scorer.rate(0.9) == "good"
    assert scorer.rate(0.85) == "good"
    assert scorer.rate(0.75) == "marginal"
    assert scorer.rate(0.70) == "marginal"
    assert scorer.rate(0.5) == "risky"
    assert scorer.rate(None) == "no_score"


def test_score_returns_result_with_rating():
    scorer = Scorer()
    result = scorer.score([EvalSignal("confidence", 0.95)])
    assert result.aggregate_score == 0.95
    assert result.rating == "good"
    assert result.signal("confidence").score == 0.95
