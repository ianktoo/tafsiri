"""Pipeline orchestration — ties the concerns together.

source records  ->  translate (provider)  ->  evaluate (evaluators)  ->  score
                ->  TranslatedRecord per (source, target language)

This module owns *control flow only*. It does no I/O of its own beyond calling
the injected provider/evaluators, and it never crashes a batch on a single
failure — provider and evaluator errors are captured on the records.

Two resilience features for rate-limited providers:
  - ``skip``: don't re-process (source, language) pairs you already have.
  - an adaptive circuit-breaker: after a run of consecutive failures, cool down
    with escalating backoff; after ``max_cooldowns`` cooldowns with no recovery,
    stop the run cleanly (raising RateLimitAbort, which carries the partial
    results collected so far).
"""

from __future__ import annotations

import time
from typing import Callable, Iterable, Optional

from tafsiri.evaluators.base import Evaluator
from tafsiri.providers.base import Translator
from tafsiri.schema import EvalResult, SourceRecord, TranslatedRecord
from tafsiri.scoring import Scorer


class RateLimitAbort(Exception):
    """Raised when the circuit-breaker gives up. Carries the records collected
    before aborting so the caller can still persist/export partial results."""

    def __init__(self, records: list[TranslatedRecord], reason: str):
        super().__init__(reason)
        self.records = records
        self.reason = reason


def run_pipeline(
    sources: Iterable[SourceRecord],
    target_langs: list[str],
    translator: Translator,
    evaluators: list[Evaluator],
    scorer: Optional[Scorer] = None,
    delay: float = 0.0,
    on_record: Optional[Callable[[TranslatedRecord], None]] = None,
    skip: Optional[set[tuple[str, str]]] = None,
    on_event: Optional[Callable[[str], None]] = None,
    fail_threshold: int = 0,
    cooldown_base: float = 5.0,
    max_cooldowns: int = 0,
    sleep: Callable[[float], None] = time.sleep,
) -> list[TranslatedRecord]:
    """Translate every source into every target language, evaluate, and score.

    ``on_record`` is called as each TranslatedRecord finishes — stream results
    to a sink (e.g. SQLite) so nothing is lost if the run is interrupted.

    ``skip`` is a set of (source_id, target_lang) to leave untouched (resume).

    Circuit-breaker (active when ``fail_threshold`` > 0): once
    ``fail_threshold`` translations fail in a row, sleep an escalating cooldown
    (``cooldown_base`` * 2**n) and keep going; after ``max_cooldowns`` such
    cooldowns without a success in between, raise ``RateLimitAbort``.
    """
    scorer = scorer or Scorer()
    skip = skip or set()
    out: list[TranslatedRecord] = []

    consecutive_fails = 0
    cooldowns_used = 0

    def emit(msg: str) -> None:
        if on_event is not None:
            on_event(msg)

    for source in sources:
        for tgt in target_langs:
            if (source.id, tgt) in skip:
                continue

            translation = translator.translate(source.text, source.src_lang, tgt)

            signals = []
            if translation.ok:
                for ev in evaluators:
                    signals.append(ev.evaluate(source, translation))
            evaluation = (scorer.score(signals) if signals
                          else EvalResult(rating="no_score"))

            record = TranslatedRecord(source=source, translation=translation,
                                      evaluation=evaluation)
            out.append(record)
            if on_record is not None:
                on_record(record)

            # --- adaptive circuit-breaker ---
            if fail_threshold > 0:
                if translation.ok:
                    consecutive_fails = 0
                    cooldowns_used = 0          # recovered — reset escalation
                else:
                    consecutive_fails += 1
                    if consecutive_fails >= fail_threshold:
                        if cooldowns_used >= max_cooldowns:
                            reason = (
                                f"Stopped after {cooldowns_used} cooldown(s) with "
                                f"persistent failures (last error: "
                                f"{translation.error}). {len(out)} item(s) processed."
                            )
                            emit(reason)
                            raise RateLimitAbort(out, reason)
                        cooldown = cooldown_base * (2 ** cooldowns_used)
                        cooldowns_used += 1
                        emit(f"{consecutive_fails} consecutive failures — cooling "
                             f"down {cooldown:.0f}s (cooldown {cooldowns_used}/"
                             f"{max_cooldowns}) before retrying.")
                        sleep(cooldown)
                        consecutive_fails = 0   # re-observe after the cooldown

            if delay:
                sleep(delay)

    return out
