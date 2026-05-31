# tafsiri

Turn raw text into **fine-tuning-ready translation datasets** for African
languages, with quality scores you can trust.

`tafsiri` ("translation" in Swahili) runs a simple pipeline:

```
source text  →  translate (Daraja AI / Babel)  →  evaluate  →  score
             →  structured training data  +  an eval report
```

It translates your text into one or more African languages using
[Daraja AI](https://daraja.ai)'s *Babel* models, evaluates each translation
several independent ways, scores it, and writes out fine-tuning data plus a
report telling you whether the quality is good enough to use. Everything is
persisted to SQLite so nothing is lost between sessions.

> **Name note:** "Daraja" is also Safaricom's M-PESA API. This project targets
> the Daraja AI **translation** API (`api.daraja.ai`), not M-PESA.

## Why it's built this way (separation of concerns)

Each stage is one module with one job, so you can swap any piece:

| Module                 | Concern                                              |
| ---------------------- | ---------------------------------------------------- |
| `sources`              | Load source text (JSONL/CSV) → `SourceRecord`        |
| `providers`            | Translation backends (`Translator` protocol)         |
| `evaluators`           | Quality signals (confidence, back-translation, judge)|
| `scoring`              | Combine signals → aggregate score + rating           |
| `pipeline`             | Orchestrate source → translate → evaluate → score    |
| `storage`              | Durable SQLite persistence (a pluggable `Sink`)      |
| `export`               | Write training data (2 formats), CSV, eval report    |
| `cli`                  | Wire it together                                     |

## Install

```powershell
uv sync                      # core
uv sync --extra dev          # + pytest
uv sync --extra ollama       # + local Ollama judge
uv sync --extra openai       # + OpenAI judge
uv sync --extra anthropic    # + Claude judge
uv sync --extra gemini       # + Gemini judge
```

Prefer pip? Core runtime deps are pinned in `requirements.txt`:

```bash
pip install -r requirements.txt   # then: pip install -e . to get the `tafsiri` command
```

Add your Daraja AI key to `.env` (gitignored):

```
DARAJA_API_KEY=dk_...
```

## Quickstart

Run the bundled emergency dataset through the full pipeline:

```powershell
uv run tafsiri run
```

That translates each message into Swahili, Yoruba, Amharic, and Creole,
evaluates with confidence + back-translation, scores each, persists to
`tafsiri.db`, and writes outputs to `out/`.

Smaller / faster trial:

```powershell
uv run tafsiri run --langs Swahili --limit 3 --no-backtranslation
```

## The three evaluators

| Evaluator          | What it measures                              | Cost              |
| ------------------ | --------------------------------------------- | ----------------- |
| `confidence`       | Babel's own confidence score                  | free (no calls)   |
| `back_translation` | Round-trips back to English, measures drift   | +1 API call each  |
| `llm_judge`        | An LLM rates adequacy + fluency (1–5)          | +1 LLM call each  |

The aggregate score is a weighted mean of whichever signals are available;
back-translation and the judge are weighted higher than self-reported
confidence. A score is bucketed into a **rating**:

- `good` ≥ 0.85 — trustworthy enough to keep as-is
- `marginal` ≥ 0.70 — usable, but flag for human review
- `risky` < 0.70 — do not rely on
- `no_score` — translation failed or nothing could be scored

### LLM-as-judge (provider-agnostic via LangChain)

The judge is any LangChain chat model. Pick it with `--judge provider:model`.
Friendly aliases: `claude`→Anthropic, `gemini`→Google, `gpt`→OpenAI.

```powershell
# local, free, private — needs a running Ollama server
uv run tafsiri run --judge ollama:llama3.1

# hosted providers (set the provider's own API key in your env)
uv run tafsiri run --judge openai:gpt-4o-mini
uv run tafsiri run --judge claude:claude-sonnet-4-6
uv run tafsiri run --judge gemini:gemini-2.0-flash
```

Install the matching extra first (`uv sync --extra openai|anthropic|gemini|ollama`).
The judge prompt lives in `tafsiri.prompts` and is overridable — see below.

## Outputs

For run `run-YYYYMMDD-HHMMSS`, written to `out/`:

| File                  | What                                                    |
| --------------------- | ------------------------------------------------------- |
| `<run>.chat.jsonl`    | Training data — chat format `{messages:[...]}`          |
| `<run>.pairs.jsonl`   | Training data — `{input, output, src_lang, tgt_lang}`   |
| `<run>.csv`           | Flat table of every translation + score                 |
| `<run>.report.json`   | The score summary / fit verdict                         |

Training files only include translations at or above `--min-rating`
(`marginal` by default, or `good`), so low-quality output never poisons your
fine-tune. All runs are also stored in `tafsiri.db`.

Example training line (chat format):

```json
{"messages": [
  {"role": "system", "content": "Translate the text from English to Swahili."},
  {"role": "user", "content": "Help is on the way."},
  {"role": "assistant", "content": "Msaada unakuja."}
], "meta": {"source_id": "flood-instruction", "rating": "good", "score": 0.91}}
```

## Persistence (SQLite)

Every run streams to `tafsiri.db` as it goes — interrupt it and finished
records are already safe. Writes are idempotent (keyed by run + source +
language), so re-running updates in place.

```powershell
uv run tafsiri runs                 # list past runs
uv run tafsiri report <run-id>      # print a stored run's report
```

## Rate limits & resuming

Translation APIs rate-limit (with good reason). `tafsiri` handles that on three
levels:

- **Per-call retry** with backoff that honors the `Retry-After` header.
- **Adaptive circuit-breaker**: after several consecutive failures it cools down
  with escalating backoff, and after a few cooldowns with no recovery it stops
  the run *cleanly* and tells you how to continue — rather than hammering the API.
- **Resume**: every successful translation is in SQLite, so you can pick up
  exactly where you left off without paying for the same calls twice.

```powershell
# gentler pacing, fewer calls
uv run tafsiri run --delay 2 --no-backtranslation

# continue an interrupted/rate-limited run — reuses what's already stored
uv run tafsiri run --run-id full-4lang --resume --delay 2
```

```powershell
# best-effort: when failures pile up, stop calling and just evaluate what
# already succeeded — no cooldowns, clean exit
uv run tafsiri run --abandon-calls
```

Tuning flags: `--delay`, `--fail-threshold` (default 5), `--cooldown` (base
seconds, doubles each time), `--max-cooldowns` (default 3; `--fail-threshold 0`
disables the breaker), `--abandon-calls` (take what you've got and move on).

## Bring your own data

Source files are domain-agnostic JSONL or CSV. Required field: `text`.
Recognized: `id`, `src_lang`/`lang`. Everything else is preserved as metadata.

```jsonl
{"id": "1", "text": "Please send help.", "src_lang": "English", "category": "medical"}
```

```powershell
uv run tafsiri run --source mydata.csv --langs Swahili,Amharic
```

### Bundled sample datasets

Ready-to-run datasets live in [`samples/`](samples/), one folder per domain —
**emergency, healthcare, finance, tech, road-accidents, conversations** (64
records total). See [`samples/README.md`](samples/README.md) for the catalog and
a step-by-step full-pipeline walkthrough.

```powershell
uv run tafsiri run --source samples/finance/finance_v1.jsonl --langs Swahili --progress
```

## Customizing prompts

All prompt text lives in the importable `tafsiri.prompts` package — nothing is
buried inline. Override per evaluator:

```python
from tafsiri.evaluators import LLMJudgeEvaluator, make_chat_model

judge = LLMJudgeEvaluator(
    make_chat_model("claude:claude-sonnet-4-6"),
    system_prompt="Your custom rubric...",
    user_builder=lambda src, sl, tl, tr: f"{sl}->{tl}: {src} == {tr}",
)
```

## CLI reference

Three commands:

| Command                      | What it does                                        |
| ---------------------------- | --------------------------------------------------- |
| `tafsiri run`                | translate → evaluate → score → persist → export     |
| `tafsiri runs`               | list runs stored in the SQLite db                   |
| `tafsiri report <run-id>`    | print the stored report for a run                   |

Flags for `tafsiri run`:

| Flag                  | Default                       | Purpose                                                        |
| --------------------- | ----------------------------- | -------------------------------------------------------------- |
| `--source`            | bundled emergency dataset     | JSONL/CSV file of source text                                  |
| `--langs`             | Swahili,Yoruba,Amharic,Creole | comma-separated target languages                               |
| `--out-dir`           | `out`                         | where training data / CSV / report are written                 |
| `--db`                | `tafsiri.db`                  | SQLite database path                                           |
| `--run-id`            | timestamp                     | run identifier (reuse with `--resume`)                         |
| `--limit`             | 0 (all)                       | only the first N source rows                                   |
| `--judge`             | off                           | LLM-as-judge model, e.g. `ollama:llama3.1`, `openai:gpt-4o-mini` |
| `--no-backtranslation`| off                           | skip the back-translation evaluator (halves API calls)         |
| `--min-rating`        | `marginal`                    | minimum rating kept in training data (`marginal` or `good`)    |
| `--good`              | 0.85                          | score threshold for the `good` rating                          |
| `--marginal`          | 0.70                          | score threshold for the `marginal` rating                      |
| `--delay`             | 0.2                           | seconds between API calls (raise to ease rate limits)          |
| `--resume`            | off                           | reuse already-stored `ok` translations for this run-id         |
| `--fail-threshold`    | 5                             | consecutive failures before a cooldown (0 disables breaker)    |
| `--cooldown`          | 5.0                           | base cooldown seconds (doubles each time)                      |
| `--max-cooldowns`     | 3                             | cooldowns to attempt before stopping cleanly                   |
| `--abandon-calls`     | off                           | on a failure streak, stop calling and evaluate what succeeded  |
| `--progress`          | off                           | live progress bar + status line (TTY only; plain output otherwise) |

Exit codes: `0` success (or clean abandon), `2` config error (e.g. missing key),
`3` stopped early by the circuit-breaker.

## Development

```powershell
uv run pytest          # full suite (58 tests), network-free — providers/judge are faked
```

## Project layout

```
src/tafsiri/
  config.py        sources.py      scoring.py      storage.py
  schema.py        providers/      evaluators/     export.py
  serialize.py     pipeline.py     cli.py          progress.py
  prompts/         importable, overridable prompt text
samples/           datasets by domain + full-pipeline guide
tests/             network-free unit tests
```

## Roadmap

- A `ghost.build` sink (persist evals/results to ghost.build alongside SQLite).
- More bundled datasets beyond the emergency example.

## Dependencies

- **[Daraja AI](https://daraja.ai)** — the translation provider (Babel models).
  Requires a `DARAJA_API_KEY`.
- **LangChain** (optional) — powers the LLM-as-judge. Pick a provider extra:
  `[openai]`, `[anthropic]` (Claude), `[gemini]`, or `[ollama]` (local).
- **requests**, **python-dotenv** — core.

## License

[MIT](LICENSE).

