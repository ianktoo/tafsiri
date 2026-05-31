"""SQLite persistence — durable storage so results survive across sessions.

Uses stdlib ``sqlite3`` (no extra dependency). Writes are idempotent: a row is
keyed by (run_id, source_id, tgt_lang), so re-running the same batch updates in
place rather than duplicating or losing data. Stream records in as the pipeline
produces them (via ``on_record``) and a crash mid-run still leaves every
finished record on disk.

This also defines the ``Sink`` protocol — the seam for other backends (a
file sink, or a future ghost.build sink) to plug in behind the same interface.
"""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any, Optional, Protocol, runtime_checkable

from tafsiri.schema import TranslatedRecord
from tafsiri.serialize import flatten_record

_SCHEMA = """
CREATE TABLE IF NOT EXISTS runs (
    run_id     TEXT PRIMARY KEY,
    created_at TEXT,
    meta       TEXT,
    summary    TEXT
);
CREATE TABLE IF NOT EXISTS records (
    run_id          TEXT NOT NULL,
    source_id       TEXT NOT NULL,
    tgt_lang        TEXT NOT NULL,
    src_lang        TEXT,
    source_text     TEXT,
    translation     TEXT,
    confidence      REAL,
    model           TEXT,
    ok              INTEGER,
    error           TEXT,
    aggregate_score REAL,
    rating          TEXT,
    speaker         TEXT,
    category        TEXT,
    signals         TEXT,
    meta            TEXT,
    PRIMARY KEY (run_id, source_id, tgt_lang)
);
CREATE INDEX IF NOT EXISTS idx_records_run ON records(run_id);
CREATE INDEX IF NOT EXISTS idx_records_rating ON records(rating);
"""


@runtime_checkable
class Sink(Protocol):
    """A destination for results. Implement these to add a new backend."""

    def start_run(self, run_id: str, meta: dict) -> None: ...
    def save_record(self, run_id: str, record: TranslatedRecord) -> None: ...
    def finish_run(self, run_id: str, summary: dict) -> None: ...
    def close(self) -> None: ...


class SQLiteStore:
    """Durable SQLite-backed sink + reader."""

    def __init__(self, path: str | Path = "tafsiri.db"):
        self.path = str(path)
        if self.path != ":memory:":
            Path(self.path).parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(self.path)
        self.conn.row_factory = sqlite3.Row
        self.conn.executescript(_SCHEMA)
        self.conn.commit()

    # --- Sink interface -------------------------------------------------
    def start_run(self, run_id: str, meta: dict, created_at: str = "") -> None:
        self.conn.execute(
            "INSERT INTO runs(run_id, created_at, meta, summary) VALUES (?,?,?,?) "
            "ON CONFLICT(run_id) DO UPDATE SET meta=excluded.meta",
            (run_id, created_at, json.dumps(meta, ensure_ascii=False), None),
        )
        self.conn.commit()

    def save_record(self, run_id: str, record: TranslatedRecord) -> None:
        r = flatten_record(record)
        self.conn.execute(
            """
            INSERT INTO records (
                run_id, source_id, tgt_lang, src_lang, source_text, translation,
                confidence, model, ok, error, aggregate_score, rating,
                speaker, category, signals, meta
            ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            ON CONFLICT(run_id, source_id, tgt_lang) DO UPDATE SET
                src_lang=excluded.src_lang, source_text=excluded.source_text,
                translation=excluded.translation, confidence=excluded.confidence,
                model=excluded.model, ok=excluded.ok, error=excluded.error,
                aggregate_score=excluded.aggregate_score, rating=excluded.rating,
                speaker=excluded.speaker, category=excluded.category,
                signals=excluded.signals, meta=excluded.meta
            """,
            (
                run_id, r["source_id"], r["tgt_lang"], r["src_lang"],
                r["source_text"], r["translation"], r["confidence"], r["model"],
                int(bool(r["ok"])), r["error"], r["aggregate_score"], r["rating"],
                r.get("speaker"), r.get("category"),
                json.dumps(r["signals"], ensure_ascii=False),
                json.dumps(r["meta"], ensure_ascii=False),
            ),
        )
        self.conn.commit()

    def finish_run(self, run_id: str, summary: dict) -> None:
        self.conn.execute(
            "UPDATE runs SET summary=? WHERE run_id=?",
            (json.dumps(summary, ensure_ascii=False), run_id),
        )
        self.conn.commit()

    def close(self) -> None:
        self.conn.close()

    # --- Read side ------------------------------------------------------
    def list_runs(self) -> list[dict]:
        rows = self.conn.execute(
            "SELECT run_id, created_at, meta, summary FROM runs ORDER BY created_at"
        ).fetchall()
        return [dict(row) for row in rows]

    def fetch_records(self, run_id: Optional[str] = None) -> list[dict]:
        if run_id is None:
            rows = self.conn.execute("SELECT * FROM records").fetchall()
        else:
            rows = self.conn.execute(
                "SELECT * FROM records WHERE run_id=?", (run_id,)).fetchall()
        out = []
        for row in rows:
            d = dict(row)
            d["signals"] = json.loads(d["signals"]) if d["signals"] else []
            d["meta"] = json.loads(d["meta"]) if d["meta"] else {}
            d["ok"] = bool(d["ok"])
            out.append(d)
        return out

    def __enter__(self) -> "SQLiteStore":
        return self

    def __exit__(self, *exc: Any) -> None:
        self.close()
