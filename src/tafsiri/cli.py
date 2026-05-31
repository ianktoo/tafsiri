"""tafsiri command-line interface.

  tafsiri run    — translate a source file, evaluate, score, persist, export
  tafsiri runs   — list past runs stored in the SQLite db
  tafsiri report — print the stored eval report for a run

Run `tafsiri <command> -h` for options.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path

from tafsiri.config import DEFAULT_TARGET_LANGUAGES, Settings
from tafsiri.evaluators import (
    BackTranslationEvaluator,
    ConfidenceEvaluator,
    LLMJudgeEvaluator,
    make_chat_model,
)
from tafsiri.export import (
    build_report,
    write_chat_jsonl,
    write_csv,
    write_pairs_jsonl,
    write_report,
)
from tafsiri.pipeline import run_pipeline
from tafsiri.providers import DarajaTranslator
from tafsiri.scoring import Scorer
from tafsiri.serialize import flatten_record
from tafsiri.sources import load_source
from tafsiri.storage import SQLiteStore


def _truncate(s, width: int) -> str:
    s = "" if s is None else str(s)
    return s if len(s) <= width else s[: width - 1] + "…"


def _print_table(records) -> None:
    cols = [("source_id", 18), ("tgt_lang", 9), ("score", 6),
            ("rating", 9), ("translation", 40)]
    print("\n" + "  ".join(f"{n:<{w}}" for n, w in cols))
    print("  ".join("-" * w for _, w in cols))
    for rec in records:
        r = flatten_record(rec)
        score = "" if r["aggregate_score"] is None else f"{r['aggregate_score']:.3f}"
        cells = [
            _truncate(r["source_id"], 18), _truncate(r["tgt_lang"], 9),
            f"{score:<6}", _truncate(r["rating"], 9),
            _truncate(r["translation"] if r["ok"] else f"ERR: {r['error']}", 40),
        ]
        print("  ".join(f"{c:<{w}}" for c, (_, w) in zip(cells, cols)))


def _print_report(report: dict) -> None:
    print("\n" + "=" * 64)
    print("EVAL REPORT")
    print("=" * 64)
    print(f"  scored/ok/total : {report.get('ok')}/{report.get('total')}")
    print(f"  avg score       : {report.get('avg_score')}")
    print(f"  lowest score    : {report.get('lowest_score')}")
    c = report.get("rating_counts", {})
    print(f"  good/marginal/risky : {c.get('good',0)}/{c.get('marginal',0)}/{c.get('risky',0)}")
    for lang, st in report.get("by_language", {}).items():
        print(f"  {lang:<10}: avg {st['avg_score']} (n={st['count']})")
    for sp, st in report.get("by_speaker", {}).items():
        print(f"  {sp:<16}: avg {st['avg_score']} (n={st['count']})")
    print(f"\n  VERDICT: {report.get('verdict')}")


def cmd_run(args: argparse.Namespace) -> int:
    settings = Settings.from_env()
    if not settings.api_key:
        print("No API key. Set DARAJA_API_KEY in .env", file=sys.stderr)
        return 2

    sources = load_source(args.source)
    if args.limit:
        sources = sources[: args.limit]
    langs = ([s.strip() for s in args.langs.split(",")] if args.langs
             else list(DEFAULT_TARGET_LANGUAGES))

    translator = DarajaTranslator(settings.api_key, base_url=settings.base_url,
                                  timeout=settings.request_timeout)

    evaluators = [ConfidenceEvaluator()]
    if not args.no_backtranslation:
        evaluators.append(BackTranslationEvaluator(translator))
    if args.judge:
        try:
            evaluators.append(LLMJudgeEvaluator(make_chat_model(args.judge)))
        except Exception as e:
            print(f"Could not init judge {args.judge!r}: {e}", file=sys.stderr)
            return 2

    scorer = Scorer(good=args.good, marginal=args.marginal)

    run_id = args.run_id or datetime.now().strftime("run-%Y%m%d-%H%M%S")
    store = SQLiteStore(args.db)
    meta = {"source": str(args.source), "languages": langs,
            "judge": args.judge, "back_translation": not args.no_backtranslation}
    store.start_run(run_id, meta, created_at=datetime.now().isoformat(timespec="seconds"))

    print(f"Run {run_id}: {len(sources)} sources x {len(langs)} langs "
          f"= {len(sources) * len(langs)} translations -> db {args.db}")

    delay = settings.request_delay if args.delay is None else args.delay
    records = run_pipeline(
        sources, langs, translator, evaluators, scorer=scorer,
        delay=delay,
        on_record=lambda rec: store.save_record(run_id, rec),
    )

    _print_table(records)

    out_dir = Path(args.out_dir)
    chat_path = out_dir / f"{run_id}.chat.jsonl"
    pairs_path = out_dir / f"{run_id}.pairs.jsonl"
    csv_path = out_dir / f"{run_id}.csv"
    report_path = out_dir / f"{run_id}.report.json"

    n_chat = write_chat_jsonl(records, chat_path, min_rating=args.min_rating)
    n_pairs = write_pairs_jsonl(records, pairs_path, min_rating=args.min_rating)
    write_csv(records, csv_path)
    report = write_report(records, report_path)
    store.finish_run(run_id, report)
    store.close()

    _print_report(report)
    print(f"\n  training (chat) : {chat_path}  ({n_chat} kept, min_rating={args.min_rating})")
    print(f"  training (pairs): {pairs_path}  ({n_pairs} kept)")
    print(f"  csv             : {csv_path}")
    print(f"  report          : {report_path}")
    print(f"  db              : {args.db}  (run_id={run_id})")
    return 0


def cmd_runs(args: argparse.Namespace) -> int:
    store = SQLiteStore(args.db)
    runs = store.list_runs()
    store.close()
    if not runs:
        print("No runs stored yet.")
        return 0
    for r in runs:
        summary = json.loads(r["summary"]) if r["summary"] else {}
        print(f"{r['run_id']}  {r['created_at']}  "
              f"avg={summary.get('avg_score')}  verdict={summary.get('verdict','')[:40]}")
    return 0


def cmd_report(args: argparse.Namespace) -> int:
    store = SQLiteStore(args.db)
    rows = store.fetch_records(args.run_id)
    store.close()
    if not rows:
        print(f"No records for run {args.run_id!r} in {args.db}", file=sys.stderr)
        return 1
    # Rebuild a report straight from stored rows (no re-translation needed).
    report = _report_from_rows(rows)
    _print_report(report)
    return 0


def _report_from_rows(rows: list[dict]) -> dict:
    total = len(rows)
    ok = sum(1 for r in rows if r["ok"])
    scores = [r["aggregate_score"] for r in rows if r["aggregate_score"] is not None]
    counts: dict[str, int] = {}
    for r in rows:
        counts[r["rating"]] = counts.get(r["rating"], 0) + 1

    def avg(v):
        return round(sum(v) / len(v), 4) if v else None

    by_lang: dict[str, list] = {}
    by_speaker: dict[str, list] = {}
    for r in rows:
        if r["aggregate_score"] is None:
            continue
        by_lang.setdefault(r["tgt_lang"], []).append(r["aggregate_score"])
        if r.get("speaker"):
            by_speaker.setdefault(r["speaker"], []).append(r["aggregate_score"])
    return {
        "total": total, "ok": ok, "avg_score": avg(scores),
        "lowest_score": min(scores) if scores else None,
        "rating_counts": counts,
        "by_language": {k: {"count": len(v), "avg_score": avg(v)} for k, v in by_lang.items()},
        "by_speaker": {k: {"count": len(v), "avg_score": avg(v)} for k, v in by_speaker.items()},
        "verdict": "(stored run)",
    }


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="tafsiri", description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="command", required=True)

    r = sub.add_parser("run", help="translate, evaluate, score, persist, export")
    r.add_argument("--source", default="data/source/emergency_v1.jsonl",
                   help="JSONL/CSV source file (default: bundled emergency dataset)")
    r.add_argument("--langs", default=None,
                   help="comma-separated target languages (default: Swahili,Yoruba,Amharic,Creole)")
    r.add_argument("--out-dir", default="out", help="output directory (default: out)")
    r.add_argument("--db", default="tafsiri.db", help="SQLite db path (default: tafsiri.db)")
    r.add_argument("--run-id", default=None, help="run id (default: timestamp)")
    r.add_argument("--judge", default=None,
                   help="LLM-as-judge model spec, e.g. ollama:llama3.1 or openai:gpt-4o-mini")
    r.add_argument("--no-backtranslation", action="store_true",
                   help="skip the back-translation evaluator")
    r.add_argument("--min-rating", choices=["good", "marginal"], default="marginal",
                   help="minimum rating to include in training data (default: marginal)")
    r.add_argument("--good", type=float, default=0.85, help="'good' threshold (default 0.85)")
    r.add_argument("--marginal", type=float, default=0.70, help="'marginal' threshold (default 0.70)")
    r.add_argument("--limit", type=int, default=0, help="only the first N source rows")
    r.add_argument("--delay", type=float, default=None,
                   help="seconds between API calls (default 0.2; raise to avoid rate limits)")
    r.set_defaults(func=cmd_run)

    rl = sub.add_parser("runs", help="list stored runs")
    rl.add_argument("--db", default="tafsiri.db")
    rl.set_defaults(func=cmd_runs)

    rp = sub.add_parser("report", help="print the stored report for a run")
    rp.add_argument("run_id")
    rp.add_argument("--db", default="tafsiri.db")
    rp.set_defaults(func=cmd_report)
    return p


def _force_utf8_stdout() -> None:
    """Translations contain non-Latin characters (e.g. Yoruba ń, Amharic
    script). On Windows the console defaults to cp1252 and crashes on them, so
    print as UTF-8 and replace anything truly unencodable rather than raising."""
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is not None:
            try:
                reconfigure(encoding="utf-8", errors="replace")
            except (ValueError, OSError):
                pass


def main(argv: list[str] | None = None) -> int:
    _force_utf8_stdout()
    args = build_parser().parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
