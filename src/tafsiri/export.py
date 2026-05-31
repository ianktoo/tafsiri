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


def _signal_score(row: dict, name: str):
    for s in row.get("signals", []):
        if s.get("name") == name:
            return s.get("score")
    return None


def _signal_detail(row: dict, name: str, key: str):
    for s in row.get("signals", []):
        if s.get("name") == name:
            return (s.get("detail") or {}).get(key)
    return None


def _all_signal_names(rows: list[dict]) -> list[str]:
    seen: list[str] = []
    for r in rows:
        for s in r.get("signals", []):
            if s.get("name") not in seen:
                seen.append(s["name"])
    return seen


def write_csv(records: Iterable[TranslatedRecord], path: str | Path) -> int:
    rows = [flatten_record(r) for r in records]
    base = ["source_id", "speaker", "category", "src_lang", "tgt_lang",
            "source_text", "translation", "confidence", "aggregate_score",
            "rating", "ok", "model", "error"]
    signal_names = _all_signal_names(rows)
    # one column per signal score, plus judge sub-scores when present.
    signal_cols = [f"eval:{n}" for n in signal_names]
    extra = []
    if "llm_judge" in signal_names:
        extra = ["judge_adequacy", "judge_fluency"]
    fields = base + signal_cols + extra

    p = _ensure_parent(path)
    with p.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        for r in rows:
            out = {k: r.get(k) for k in base}
            for n in signal_names:
                out[f"eval:{n}"] = _signal_score(r, n)
            if extra:
                out["judge_adequacy"] = _signal_detail(r, "llm_judge", "adequacy")
                out["judge_fluency"] = _signal_detail(r, "llm_judge", "fluency")
            writer.writerow(out)
    return len(rows)


def _avg(vals):
    return round(sum(vals) / len(vals), 4) if vals else None


def build_report_from_rows(rows: list[dict]) -> dict:
    """The fit-assessment / score summary, computed from flat rows (works for
    both freshly-run records and rows fetched from SQLite)."""
    total = len(rows)
    ok = sum(1 for r in rows if r["ok"])
    scores = [r["aggregate_score"] for r in rows if r["aggregate_score"] is not None]

    counts = {"good": 0, "marginal": 0, "risky": 0, "no_score": 0}
    for r in rows:
        counts[r["rating"]] = counts.get(r["rating"], 0) + 1

    by_lang: dict[str, list[float]] = {}
    by_speaker: dict[str, list[float]] = {}
    by_signal: dict[str, list[float]] = {}
    for r in rows:
        for s in r.get("signals", []):
            if s.get("score") is not None:
                by_signal.setdefault(s["name"], []).append(s["score"])
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
        "by_signal": {k: {"count": len(v), "avg_score": _avg(v)}
                      for k, v in sorted(by_signal.items())},
        "verdict": verdict,
    }


def build_report(records: list[TranslatedRecord]) -> dict:
    return build_report_from_rows([flatten_record(r) for r in records])


def write_report(records: list[TranslatedRecord], path: str | Path) -> dict:
    report = build_report(records)
    p = _ensure_parent(path)
    p.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    return report


def _table(headers: list[str], rows: list[list]) -> str:
    line = "| " + " | ".join(headers) + " |"
    sep = "| " + " | ".join("---" for _ in headers) + " |"
    body = "\n".join("| " + " | ".join(str(c) for c in r) + " |" for r in rows)
    return "\n".join([line, sep, body]) if rows else ""


def render_markdown(report: dict, run_id: str | None = None,
                    rows: list[dict] | None = None) -> str:
    c = report.get("rating_counts", {})
    title = f"# Findings — {run_id}" if run_id else "# Findings"
    out = [title, "", f"**Verdict:** {report.get('verdict','')}", "",
           "## Summary", "",
           _table(["metric", "value"], [
               ["translations (ok / total)", f"{report.get('ok')} / {report.get('total')}"],
               ["avg score", report.get("avg_score")],
               ["lowest score", report.get("lowest_score")],
               ["good / marginal / risky",
                f"{c.get('good',0)} / {c.get('marginal',0)} / {c.get('risky',0)}"],
           ])]

    if report.get("by_signal"):
        out += ["", "## By evaluation signal", "",
                _table(["signal", "n", "avg score"],
                       [[k, v["count"], v["avg_score"]]
                        for k, v in report["by_signal"].items()])]
    if report.get("by_language"):
        out += ["", "## By language", "",
                _table(["language", "n", "avg score"],
                       [[k, v["count"], v["avg_score"]]
                        for k, v in report["by_language"].items()])]
    if report.get("by_speaker"):
        out += ["", "## By speaker", "",
                _table(["speaker", "n", "avg score"],
                       [[k, v["count"], v["avg_score"]]
                        for k, v in report["by_speaker"].items()])]
    if rows:
        out += ["", "## Per translation", "",
                _table(["source", "lang", "score", "rating"],
                       [[r["source_id"], r["tgt_lang"],
                         (round(r["aggregate_score"], 3)
                          if r["aggregate_score"] is not None else "—"),
                         r["rating"]] for r in rows])]
    return "\n".join(out) + "\n"
