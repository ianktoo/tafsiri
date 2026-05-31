"""Core data structures shared across the pipeline.

These are plain dataclasses so every stage speaks the same language and tests
can build them without touching the network.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional


@dataclass
class SourceRecord:
    """A single piece of source text to be translated.

    Domain-agnostic: well-known fields are explicit; anything else (e.g.
    ``speaker``, ``category`` for the emergency dataset) lives in ``meta``.
    """

    id: str
    text: str
    src_lang: str = "English"
    meta: dict[str, Any] = field(default_factory=dict)


@dataclass
class Translation:
    """The result of translating one SourceRecord into one target language."""

    src_lang: str
    tgt_lang: str
    text: Optional[str] = None        # the translated text
    confidence: Optional[float] = None
    model: Optional[str] = None
    ok: bool = False
    error: Optional[str] = None
    raw: Optional[dict] = None         # raw provider payload, for debugging


@dataclass
class EvalSignal:
    """One quality signal from a single evaluator, normalized to 0..1."""

    name: str
    score: Optional[float]             # 0..1, or None if not applicable
    detail: dict[str, Any] = field(default_factory=dict)


@dataclass
class EvalResult:
    """Aggregated evaluation for one translation."""

    signals: list[EvalSignal] = field(default_factory=list)
    aggregate_score: Optional[float] = None   # 0..1
    rating: str = "no_score"                   # good | marginal | risky | no_score

    def signal(self, name: str) -> Optional[EvalSignal]:
        for s in self.signals:
            if s.name == name:
                return s
        return None


@dataclass
class TranslatedRecord:
    """A source record + one translation + its evaluation. The unit the
    pipeline produces and that export/scoring consume."""

    source: SourceRecord
    translation: Translation
    evaluation: EvalResult = field(default_factory=EvalResult)
