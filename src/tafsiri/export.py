"""Export results: fine-tuning training data, a CSV, and an eval report.

Two training formats (you chose both):
  - chat messages JSONL : {"messages": [system, user, assistant], "meta": {...}}
  - input/output pairs  : {"input", "output", "src_lang", "tgt_lang", "meta"}

Training exports filter by rating so low-quality translations don't poison the
fine-tune. The eval report is the "give it a score" summary.
"""

from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Iterable

from tafsiri.schema import TranslatedRecord
from tafsiri.serialize import flatten_record

_RATING_ORDER = {"risky": 0, "no_score": 0, "marginal": 1, "good": 2}


def _passes(rating: str, min_rating: str) -> bool:
    return _RATING_ORDER.get(rating, 0) >= _RATING_ORDER.get(min_rating, 1)


def _ensure_parent(path: str | Path) -> Path:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    return p


def _trainable(records: Iterable[TranslatedRecord], min_rating: str):
    for rec in records:
        if rec.translation.ok and rec.translation.text and _passes(
                rec.evaluation.rating, min_rating):
            yield rec


def write_chat_jsonl(records: Iterable[TranslatedRecord], path: str | Path,
                     min_rating: str = "marginal") -> int:
    p = _ensure_parent(path)
    n = 0
    with p.open("w", encoding="utf-8") as f:
        for rec in _trainable(records, min_rating):
            t, s = rec.translation, rec.source
            obj = {
                "messages": [
                    {"role": "system",
                     "content": f"Translate the text from {t.src_lang} to {t.tgt_lang}."},
                    {"role": "user", "content": s.text},
                    {"role": "assistant", "content": t.text},
                ],
                "meta": {
                    "source_id": s.id, "tgt_lang": t.tgt_lang,
                    "rating": rec.evaluation.rating,
                    "score": rec.evaluation.aggregate_score, **s.meta,
                },
            }
            f.write(json.dumps(obj, ensure_ascii=False) + "\n")
            n += 1
    return n


def write_pairs_jsonl(records: Iterable[TranslatedRecord], path: str | Path,
                      min_rating: str = "marginal") -> int:
    p = _ensure_parent(path)
    n = 0
    with p.open("w", encoding="utf-8") as f:
        for rec in _trainable(records, min_rating):
            t, s = rec.translation, rec.source
            obj = {
                "input": s.text, "output": t.text,
                "src_lang": t.src_lang, "tgt_lang": t.tgt_lang,
                "meta": {
                    "source_id": s.id, "rating": rec.evaluation.rating,
                    "score": rec.evaluation.aggregate_score, **s.meta,
                },
            }
            f.write(json.dumps(obj, ensure_ascii=False) + "\n")
            n += 1
    return n


def write_csv(records: Iterable[TranslatedRecord], path: str | Path) -> int:
    fields = ["source_id", "speaker", "category", "src_lang", "tgt_lang",
              "source_text", "translation", "confidence", "aggregate_score",
              "rating", "ok", "model", "error"]
    p = _ensure_parent(path)
    rows = [flatten_record(r) for r in records]
    with p.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        for r in rows:
            writer.writerow({k: r.get(k) for k in fields})
    return len(rows)


def build_report(records: list[TranslatedRecord]) -> dict:
    """The fit-assessment / score summary."""
    rows = [flatten_record(r) for r in records]
    total = len(rows)
    ok = sum(1 for r in rows if r["ok"])
    scores = [r["aggregate_score"] for r in rows
              if r["aggregate_score"] is not None]

    counts = {"good": 0, "marginal": 0, "risky": 0, "no_score": 0}
    for r in rows:
        counts[r["rating"]] = counts.get(r["rating"], 0) + 1

    def _avg(vals):
        return round(sum(vals) / len(vals), 4) if vals else None

    by_lang: dict[str, list[float]] = {}
    by_speaker: dict[str, list[float]] = {}
    for r in rows:
        if r["aggregate_score"] is None:
            continue
        by_lang.setdefault(r["tgt_lang"], []).append(r["aggregate_score"])
        sp = r.get("speaker")
        if sp:
            by_speaker.setdefault(sp, []).append(r["aggregate_score"])

    if not ok:
        verdict = "BLOCKED — no successful translations (check key / endpoint)."
    elif counts["risky"]:
        verdict = ("NOT A FIT for unmonitored use — some translations fall below "
                   "the safety bar; human review required.")
    elif counts["marginal"]:
        verdict = ("CONDITIONAL FIT — usable with a human-in-the-loop review of "
                   "flagged (marginal) translations.")
    else:
        verdict = "GOOD FIT — all scored translations clear the safety bar."

    return {
        "total": total, "ok": ok,
        "avg_score": _avg(scores),
        "lowest_score": min(scores) if scores else None,
        "rating_counts": counts,
        "by_language": {k: {"count": len(v), "avg_score": _avg(v)}
                        for k, v in sorted(by_lang.items())},
        "by_speaker": {k: {"count": len(v), "avg_score": _avg(v)}
                       for k, v in sorted(by_speaker.items())},
        "verdict": verdict,
    }


def write_report(records: list[TranslatedRecord], path: str | Path) -> dict:
    report = build_report(records)
    p = _ensure_parent(path)
    p.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    return report
