# Sample datasets

Ready-to-run source datasets, one folder per domain. Each file is JSONL where
every line has at least `text` (required) and `src_lang`, plus domain metadata
(`domain`, `category`, and sometimes `speaker`) preserved through the pipeline.

| Domain | File | What's inside |
| ------ | ---- | ------------- |
| Emergency | [`emergency/emergency_v1.jsonl`](emergency/emergency_v1.jsonl) | Casualty ↔ first-responder messages (medical, disaster, security) |
| Healthcare | [`healthcare/healthcare_v1.jsonl`](healthcare/healthcare_v1.jsonl) | Appointments, prescriptions, maternal & chronic care |
| Finance | [`finance/finance_v1.jsonl`](finance/finance_v1.jsonl) | Mobile money, loans, fraud alerts, financial literacy |
| Tech | [`tech/tech_v1.jsonl`](tech/tech_v1.jsonl) | Support, troubleshooting, security, notifications |
| Road accidents | [`road-accidents/road_accidents_v1.jsonl`](road-accidents/road_accidents_v1.jsonl) | Incident reports, responder instructions, road safety |
| Conversations | [`conversations/conversations_v1.jsonl`](conversations/conversations_v1.jsonl) | Everyday greetings, directions, market, small talk |

## Full pipeline setup

A complete run, start to finish.

**1. Install and add your key**

```powershell
uv sync                                  # core deps
cp .env.example .env                     # then edit in your real key
```

**2. Pick a sample and do a quick trial** (one language, few rows, with a live bar)

```powershell
uv run tafsiri run --source samples/finance/finance_v1.jsonl `
  --langs Swahili --limit 3 --progress
```

**3. Run a full domain across several languages**

```powershell
uv run tafsiri run --source samples/healthcare/healthcare_v1.jsonl `
  --langs Swahili,Yoruba,Amharic,Creole --progress
```

**4. (Optional) Add an LLM-as-judge** - choose any provider:

```powershell
uv sync --extra ollama        # local, free
uv run tafsiri run --source samples/tech/tech_v1.jsonl --judge ollama:llama3.1

uv sync --extra anthropic     # or openai / gemini
uv run tafsiri run --source samples/tech/tech_v1.jsonl --judge claude:claude-sonnet-4-6
```

**5. Find your outputs** - in `out/`:

- `<run-id>.chat.jsonl` and `<run-id>.pairs.jsonl` - fine-tuning data
- `<run-id>.csv` - every translation + score
- `<run-id>.report.json` - the score summary / verdict

**6. Review and resume**

```powershell
uv run tafsiri runs                          # list stored runs
uv run tafsiri report <run-id>               # print a run's report
uv run tafsiri run --run-id <run-id> --resume   # finish a rate-limited run
```

If you hit rate limits, see the **Rate limits & resuming** section in the main
[README](../README.md) - `--delay`, the circuit-breaker, and `--abandon-calls`.

## Bring your own

Drop a JSONL or CSV anywhere and point `--source` at it. Only `text` is
required; `id`, `src_lang`/`lang` are recognized, and everything else is kept as
metadata for the report breakdowns.

```jsonl
{"id": "1", "text": "Please send help.", "src_lang": "English", "domain": "mydomain"}
```
