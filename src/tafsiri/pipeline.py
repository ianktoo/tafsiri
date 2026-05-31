"""Pipeline orchestration — ties the concerns together.

source records  ->  translate (provider)  ->  evaluate (evaluators)  ->  score
                ->  TranslatedRecord per (source, target language)

This module owns *control flow only*. It does no I/O of its own beyond calling
the injected provider/evaluators, and it never crashes a batch — provider and
evaluator failures are captured on the records.
"""

from __future__ import annotations

import time
from typing import Callable, Iterable, Optional

from tafsiri.evaluators.base import Evaluator
from tafsiri.providers.base import Translator
from tafsiri.schema import EvalResult, SourceRecord, TranslatedRecord
from tafsiri.scoring import Scorer


def run_pipeline(
    sources: Iterable[SourceRecord],
    target_langs: list[str],
    translator: Translator,
    evaluators: list[Evaluator],
    scorer: Optional[Scorer] = None,
    delay: float = 0.0,
    on_record: Optional[Callable[[TranslatedRecord], None]] = None,
) -> list[TranslatedRecord]:
    """Translate every source into every target language, evaluate, and score.

    ``on_record`` is called as each TranslatedRecord is finished — use it to
    stream results to a sink (e.g. SQLite) so nothing is lost if the run is
    interrupted partway.
    """
    scorer = scorer or Scorer()
    out: list[TranslatedRecord] = []

    for source in sources:
        for tgt in target_langs:
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
            if delay:
                time.sleep(delay)

    return out
