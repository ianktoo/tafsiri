"""Shared (de)serialization helpers so storage, CSV, and reports agree on shape."""

from __future__ import annotations

from typing import Any

from tafsiri.schema import (
    EvalResult,
    EvalSignal,
    SourceRecord,
    TranslatedRecord,
    Translation,
)


def signals_to_list(signals: list[EvalSignal]) -> list[dict]:
    return [{"name": s.name, "score": s.score, "detail": s.detail} for s in signals]


def flatten_record(rec: TranslatedRecord) -> dict[str, Any]:
    """One flat dict per (source, target language) — the common row shape used
    by SQLite, CSV export, and the eval report."""
    s, t, e = rec.source, rec.translation, rec.evaluation
    row = {
        "source_id": s.id,
        "src_lang": t.src_lang,
        "tgt_lang": t.tgt_lang,
        "source_text": s.text,
        "translation": t.text,
        "confidence": t.confidence,
        "model": t.model,
        "ok": t.ok,
        "error": t.error,
        "aggregate_score": e.aggregate_score,
        "rating": e.rating,
        "signals": signals_to_list(e.signals),
        "meta": dict(s.meta),
    }
    # Hoist a couple of common meta keys to top level for convenient querying.
    for k in ("speaker", "category"):
        if k in s.meta:
            row[k] = s.meta[k]
    return row


def record_from_row(row: dict[str, Any]) -> TranslatedRecord:
    """Inverse of ``flatten_record`` — rebuild a TranslatedRecord from a stored
    row (e.g. a SQLite fetch) so cached results can be reused on resume."""
    meta = dict(row.get("meta") or {})
    src_lang = row.get("src_lang") or "English"
    source = SourceRecord(id=row["source_id"], text=row.get("source_text") or "",
                          src_lang=src_lang, meta=meta)
    translation = Translation(
        src_lang=src_lang, tgt_lang=row["tgt_lang"], text=row.get("translation"),
        confidence=row.get("confidence"), model=row.get("model"),
        ok=bool(row.get("ok")), error=row.get("error"),
    )
    signals = [EvalSignal(name=s.get("name"), score=s.get("score"),
                          detail=s.get("detail") or {})
               for s in (row.get("signals") or [])]
    evaluation = EvalResult(signals=signals,
                            aggregate_score=row.get("aggregate_score"),
                            rating=row.get("rating") or "no_score")
    return TranslatedRecord(source=source, translation=translation,
                            evaluation=evaluation)
