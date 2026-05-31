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
    build_report_from_rows,
    render_markdown,
    write_chat_jsonl,
    write_csv,
    write_pairs_jsonl,
    write_report,
)
from tafsiri import ui
from tafsiri.pipeline import RateLimitAbort, run_pipeline
from tafsiri.progress import Progress
from tafsiri.providers import build_translator
from tafsiri.scoring import Scorer
from tafsiri.serialize import flatten_record, record_from_row
from tafsiri.sources import load_source
from tafsiri.storage import SQLiteStore


def cmd_run(args: argparse.Namespace) -> int:
    settings = Settings.from_env()

    sources = load_source(args.source)
    if args.limit:
        sources = sources[: args.limit]
    langs = ([s.strip() for s in args.langs.split(",")] if args.langs
             else list(DEFAULT_TARGET_LANGUAGES))

    try:
        translator = build_translator(
            args.engine, daraja_key=settings.api_key,
            base_url=settings.base_url, timeout=settings.request_timeout)
    except (ValueError, ImportError) as e:
        print(f"Could not init engine {args.engine!r}: {e}", file=sys.stderr)
        return 2

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
            "engine": args.engine, "judge": args.judge,
            "back_translation": not args.no_backtranslation}
    store.start_run(run_id, meta, created_at=datetime.now().isoformat(timespec="seconds"))

    # Resume: reuse already-successful (source, lang) pairs from the db.
    skip: set[tuple[str, str]] = set()
    cached: list = []
    if args.resume:
        for row in store.fetch_records(run_id):
            if row["ok"]:
                cached.append(record_from_row(row))
                skip.add((row["source_id"], row["tgt_lang"]))
        if skip:
            print(f"Resuming run {run_id}: reusing {len(skip)} stored translation(s).")

    total = len(sources) * len(langs)
    print(f"Run {run_id}: {len(sources)} sources x {len(langs)} langs = {total} "
          f"translations ({len(skip)} cached, {total - len(skip)} to fetch) -> db {args.db}")

    delay = settings.request_delay if args.delay is None else args.delay
    progress = Progress(total - len(skip), enabled=args.progress)

    def _on_record(rec):
        store.save_record(run_id, rec)
        progress.update(
            label=f"{rec.source.id} → {rec.translation.tgt_lang}",
            ok=rec.translation.ok)

    aborted = None
    try:
        new_records = run_pipeline(
            sources, langs, translator, evaluators, scorer=scorer,
            delay=delay,
            on_record=_on_record,
            skip=skip,
            on_event=lambda msg: progress.note(f"  ⏳ {msg}"),
            fail_threshold=args.fail_threshold,
            cooldown_base=args.cooldown,
            max_cooldowns=args.max_cooldowns,
            abandon=args.abandon_calls,
        )
    except RateLimitAbort as e:
        new_records = e.records
        aborted = e.reason
    finally:
        progress.finish()

    records = cached + new_records
    flat_rows = [flatten_record(r) for r in records]
    ui.render_results(flat_rows)

    out_dir = Path(args.out_dir)
    chat_path = out_dir / f"{run_id}.chat.jsonl"
    pairs_path = out_dir / f"{run_id}.pairs.jsonl"
    csv_path = out_dir / f"{run_id}.csv"
    report_path = out_dir / f"{run_id}.report.json"

    n_chat = write_chat_jsonl(records, chat_path, min_rating=args.min_rating)
    n_pairs = write_pairs_jsonl(records, pairs_path, min_rating=args.min_rating)
    write_csv(records, csv_path)
    report = write_report(records, report_path)
    md_path = out_dir / f"{run_id}.report.md"
    md_path.write_text(
        render_markdown(report, run_id, [flatten_record(r) for r in records]),
        encoding="utf-8")
    store.finish_run(run_id, report)
    store.close()

    ui.render_report(report, run_id)
    ui.info(f"training (chat) : {chat_path}  ({n_chat} kept, min_rating={args.min_rating})")
    ui.info(f"training (pairs): {pairs_path}  ({n_pairs} kept)")
    ui.info(f"csv             : {csv_path}")
    ui.info(f"report (json)   : {report_path}")
    ui.info(f"report (md)     : {md_path}")
    ui.info(f"db              : {args.db}  (run_id={run_id})")

    if aborted:
        resume_cmd = (f"tafsiri run --run-id {run_id} --resume "
                      f"--delay {max(delay, 2.0):.0f}")
        ui.render_stopped(aborted, resume_cmd)
        return 3
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

    report = build_report_from_rows(rows)

    if args.format == "json":
        text = json.dumps(report, ensure_ascii=False, indent=2)
    elif args.format == "md":
        text = render_markdown(report, args.run_id, rows)
    else:  # text
        if args.out:
            print("--out is only used with --format json|md", file=sys.stderr)
        ui.render_report(report, args.run_id)
        return 0

    if args.out:
        Path(args.out).write_text(text, encoding="utf-8")
        print(f"wrote {args.format} findings -> {args.out}")
    else:
        print(text)
    return 0


def cmd_init(args: argparse.Namespace) -> int:
    from tafsiri import interactive
    return interactive.run_setup()


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="tafsiri", description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    # Subcommand is optional: bare `tafsiri` launches the interactive wizard.
    sub = p.add_subparsers(dest="command", required=False)

    sub.add_parser("init", help="interactive setup (key, test, judge)").set_defaults(
        func=cmd_init)

    r = sub.add_parser("run", help="translate, evaluate, score, persist, export")
    r.add_argument("--source", default="samples/emergency/emergency_v1.jsonl",
                   help="JSONL/CSV source file (default: bundled emergency sample)")
    r.add_argument("--engine", default="daraja",
                   help="translation engine: 'daraja' (default) or "
                        "'llm:<provider>:<model>' e.g. llm:claude:claude-sonnet-4-6")
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
    r.add_argument("--resume", action="store_true",
                   help="skip (source, lang) pairs already stored ok for this run-id")
    r.add_argument("--fail-threshold", type=int, default=5,
                   help="consecutive failures before a cooldown (0 disables; default 5)")
    r.add_argument("--cooldown", type=float, default=5.0,
                   help="base cooldown seconds, doubles each time (default 5)")
    r.add_argument("--max-cooldowns", type=int, default=3,
                   help="cooldowns to attempt before stopping the run (default 3)")
    r.add_argument("--abandon-calls", action="store_true",
                   help="on a run of failures, stop calling immediately and just "
                        "evaluate/export what succeeded so far (no cooldowns, clean exit)")
    r.add_argument("--progress", action="store_true",
                   help="show a live progress bar + status line (TTY only; "
                        "plain output otherwise)")
    r.set_defaults(func=cmd_run)

    rl = sub.add_parser("runs", help="list stored runs")
    rl.add_argument("--db", default="tafsiri.db")
    rl.set_defaults(func=cmd_runs)

    rp = sub.add_parser("report", help="print or export the stored report for a run")
    rp.add_argument("run_id")
    rp.add_argument("--db", default="tafsiri.db")
    rp.add_argument("--format", choices=["text", "json", "md"], default="text",
                    help="output format (default: text to console)")
    rp.add_argument("--out", default=None,
                    help="write to this file instead of stdout (json/md)")
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
    if getattr(args, "func", None) is None:
        # bare `tafsiri` — launch the guided wizard (or help if non-interactive)
        from tafsiri import interactive
        return interactive.run_wizard()
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
