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
uv sync --extra judge        # + LangChain (LLM-as-judge)
uv sync --extra ollama       # + local Ollama judge support
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

The judge is any LangChain chat model. Pick the provider with `--judge`:

```powershell
# local, free, private — needs a running Ollama server
uv run tafsiri run --judge ollama:llama3.1

# hosted providers (set the provider's API key in your env)
uv run tafsiri run --judge openai:gpt-4o-mini
uv run tafsiri run --judge anthropic:claude-sonnet-4-6
```

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

## Bring your own data

Source files are domain-agnostic JSONL or CSV. Required field: `text`.
Recognized: `id`, `src_lang`/`lang`. Everything else is preserved as metadata.

```jsonl
{"id": "1", "text": "Please send help.", "src_lang": "English", "category": "medical"}
```

```powershell
uv run tafsiri run --source mydata.csv --langs Swahili,Amharic
```

The bundled emergency dataset (`data/source/emergency_v1.jsonl`) pairs
**affected-party** and **first-responder** messages across medical, disaster,
public-health, and security scenarios — the report breaks scores down by
speaker and language.

## Development

```powershell
uv run pytest          # full suite, network-free (providers/judge are faked)
```

## Project layout

```
src/tafsiri/
  config.py        sources.py      scoring.py      storage.py
  schema.py        providers/      evaluators/     export.py
  serialize.py     pipeline.py     cli.py
data/source/       emergency_v1.jsonl   (bundled example dataset)
tests/             network-free unit tests
```

## Roadmap

- A `ghost.build` sink (persist evals/results to ghost.build alongside SQLite).
- Back-translation enabled by default once provider rate limits allow.

## Dependencies

- **[Daraja AI](https://daraja.ai)** — the translation provider (Babel models).
  Requires a `DARAJA_API_KEY`.
- **LangChain** (optional, `[judge]`) — powers the LLM-as-judge evaluator.
- **requests**, **python-dotenv** — core.

## License

[MIT](LICENSE).

