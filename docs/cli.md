# CLI reference

`tafsiri` is the command-line entry point. Run it with `uv run tafsiri ...` in
the repo, or just `tafsiri ...` once installed (`pipx install tafsiri` / from the
release wheel).

```
tafsiri [command] [options]
```

Commands: [`init`](#tafsiri-init) · [`run`](#tafsiri-run) ·
[`runs`](#tafsiri-runs) · [`report`](#tafsiri-report). With **no command**, it
launches the [interactive wizard](#tafsiri-no-command).

## Global behavior

- **Colors** are on by default (via `rich`) and auto-disable when output isn't a
  terminal. Set `NO_COLOR=1` to force plain text.
- **Interactive prompts** only appear on a real TTY. In CI, pipes, or with
  redirected stdin they never block - drive everything with flags instead.
- **Deterministic**: flags fully specify a run. The wizard is a convenience that
  ends up calling `run` with the same flags.
- **Exit codes**: `0` success (or clean `--abandon-calls`), `2` configuration
  error (e.g. missing key / bad engine), `3` stopped early by the circuit-breaker.

---

## `tafsiri` (no command)

Launches the guided wizard: ensures a key (runs setup if missing), then prompts
for engine, dataset, languages, and an optional judge, shows a summary, and runs
the pipeline. Requires an interactive terminal; otherwise it prints guidance and
exits `2`.

```bash
uv run tafsiri
```

---

## `tafsiri init`

Interactive setup. Prompts for your Daraja API key (input masked), writes it to
`.env` (gitignored), offers a one-call live key test, and detects local Ollama
models to suggest as a free judge.

```bash
uv run tafsiri init
```

The key is only ever shown masked (`dk_dev…f4e9`) and is never echoed or logged.

---

## `tafsiri run`

The core pipeline: translate a source file into one or more languages, evaluate
each translation, score it, persist to SQLite, and write training data + reports.

```bash
uv run tafsiri run [options]
```

### Options

| Flag | Default | Description |
| ---- | ------- | ----------- |
| `--source PATH` | `samples/emergency/emergency_v1.jsonl` | JSONL/CSV source file |
| `--engine SPEC` | `daraja` | `daraja` or `llm:<provider>:<model>` (e.g. `llm:claude:claude-sonnet-4-6`) |
| `--langs LIST` | `Swahili,Yoruba,Amharic,Creole` | comma-separated target languages |
| `--judge SPEC` | off | LLM-as-judge model, e.g. `ollama:llama3.1`, `openai:gpt-4o-mini`, `claude:...` |
| `--no-backtranslation` | off | skip the back-translation evaluator (halves API calls) |
| `--min-rating {good,marginal}` | `marginal` | minimum rating kept in training data |
| `--good FLOAT` | `0.85` | score threshold for the `good` rating |
| `--marginal FLOAT` | `0.70` | score threshold for the `marginal` rating |
| `--limit N` | `0` (all) | only the first N source rows |
| `--delay SECONDS` | `0.2` | spacing between API calls; raise to ease rate limits |
| `--concurrency N` | `1` | parallel worker threads (I/O-bound); shares a rate limiter spaced by `--delay` |
| `--resume` | off | reuse already-stored `ok` translations for this `--run-id` |
| `--fail-threshold N` | `5` | consecutive failures before a cooldown (`0` disables the breaker) |
| `--cooldown SECONDS` | `5` | base cooldown, doubles each time |
| `--max-cooldowns N` | `3` | cooldowns to attempt before stopping cleanly |
| `--abandon-calls` | off | on a failure streak, stop calling and evaluate what succeeded |
| `--progress` | off | live progress bar + status line (TTY only) |
| `--out-dir DIR` | `~/.tafsiri/out` | output directory |
| `--db PATH` | `~/.tafsiri/tafsiri.db` | SQLite database path |
| `--run-id ID` | timestamp | run identifier (reuse with `--resume`) |

By default everything is stored under `~/.tafsiri/` (one per-user location that
works the same on every OS), not the current folder. Override per run with
`--out-dir` / `--db`, or globally with the `TAFSIRI_HOME` env var.

### Outputs (in `--out-dir`)

- `<run-id>.chat.jsonl` and `<run-id>.pairs.jsonl` - fine-tuning data (filtered by `--min-rating`)
- `<run-id>.csv` - every translation with aggregate and per-signal scores
- `<run-id>.report.json` and `<run-id>.report.md` - the eval summary
- everything is also written to the SQLite db

---

## `tafsiri runs`

List runs stored in the database.

```bash
uv run tafsiri runs [--db tafsiri.db]
```

---

## `tafsiri report`

Print or export the stored report for a run, without re-running anything.

```bash
uv run tafsiri report <run-id> [--db tafsiri.db] [--format text|json|md] [--out FILE]
```

| Flag | Default | Description |
| ---- | ------- | ----------- |
| `--format {text,json,md}` | `text` | console table, JSON, or Markdown |
| `--out FILE` | stdout | write to a file (json/md) |
| `--db PATH` | `tafsiri.db` | database to read from |

```bash
uv run tafsiri report full-4lang --format md --out findings.md
```

---

## Recipes

```bash
# quick trial: one language, 3 rows, live progress
uv run tafsiri run --langs Swahili --limit 3 --progress

# full run across four languages, with a free local judge
uv run tafsiri run --langs Swahili,Yoruba,Amharic,Creole --judge ollama:qwen2.5:7b-instruct

# faster on a generous key: 4 workers, calls spaced 0.5s
uv run tafsiri run --concurrency 4 --delay 0.5

# continue a rate-limited / interrupted run (reuses stored translations)
uv run tafsiri run --run-id myrun --resume --delay 2

# best-effort: when failures pile up, stop and evaluate what worked
uv run tafsiri run --abandon-calls

# compare a general LLM against Babel on the same inputs
uv run tafsiri run --engine llm:openai:gpt-4o-mini --run-id gpt-baseline

# bring your own data
uv run tafsiri run --source mydata.csv --langs Swahili,Amharic
```

## Environment variables

| Variable | Purpose |
| -------- | ------- |
| `DARAJA_API_KEY` | required for the `daraja` engine (set in `.env`) |
| `OPENAI_API_KEY` / `ANTHROPIC_API_KEY` / `GOOGLE_API_KEY` | for the matching `--judge` / `llm:` provider |
| `TAFSIRI_HOME` | base dir for the db + outputs (default `~/.tafsiri`) |
| `NO_COLOR` | set to force plain (uncolored) output |

Ollama needs no key - just a running `ollama serve`.

See also: [`docs/evals.md`](evals.md) for what the scores mean, and the main
[README](../README.md) for concepts and install.
