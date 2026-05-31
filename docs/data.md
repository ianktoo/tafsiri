# Data preparation

There are two kinds of data in tafsiri:

1. **Inputs you prepare** - the source text to translate.
2. **Outputs tafsiri produces** - evaluated, fine-tuning-ready datasets + reports.

This page is the spec for both.

---

## 1. Input format

Source files are **JSONL** (recommended) or **CSV**, UTF-8 encoded. One record
per line/row. The loader is domain-agnostic: a few fields are recognized, and
**everything else is preserved** so your domain metadata flows through to the
reports.

### Fields

| Field | Required | Aliases accepted | Meaning |
| ----- | -------- | ---------------- | ------- |
| `text` | **yes** | `source_text`, `input` | the text to translate |
| `id` | no | - | stable identifier (auto-assigned `row-N` if missing) |
| `src_lang` | no | `source_lang`, `lang`, `from` | source language (default: `English`) |
| *(anything else)* | no | - | kept verbatim under `meta` and surfaced in reports |

Two meta keys get special treatment in reports if present: **`speaker`** and
**`category`** (they become their own breakdown columns). `domain` is a useful
convention too.

### JSONL (recommended)

```jsonl
{"id": "flood-report", "text": "There is a flood in our village.", "src_lang": "English", "domain": "emergency", "speaker": "affected_party", "category": "natural_disaster"}
{"id": "greeting", "text": "Good morning, how are you?", "domain": "conversations", "category": "greeting"}
```

### CSV

Column headers map to the same field names. Unknown columns become `meta`.

```csv
id,text,src_lang,domain,category
c1,Please send help.,English,emergency,medical
```

```bash
uv run tafsiri run --source mydata.csv --langs Swahili,Amharic
```

### Conventions

- **Location / naming**: bundled datasets live at
  `samples/<domain>/<name>_vN.jsonl` (e.g. `samples/finance/finance_v1.jsonl`).
  Version with `_v1`, `_v2`, ... so results stay comparable. Your own data can
  live anywhere - just point `--source` at it.
- **One idea per row.** Shorter, self-contained sentences translate and
  back-translate more reliably than long multi-clause paragraphs.
- **Stable, unique `id`s.** They key the SQLite rows and enable `--resume`;
  duplicates collide.
- **Trim whitespace**, drop empty `text` rows, and keep the file UTF-8.

---

## 2. Output format

A run writes to `~/.tafsiri/out/` by default (override with `--out-dir`), named
by run id, plus the SQLite db. Two of the files are the *prepared training data*.

### Training data - chat messages (`<run>.chat.jsonl`)

For instruction / chat fine-tuning. Filtered by `--min-rating` (default
`marginal`), so low-quality translations are excluded.

```json
{"messages": [
  {"role": "system", "content": "Translate the text from English to Swahili."},
  {"role": "user", "content": "Good morning, how are you?"},
  {"role": "assistant", "content": "Habari za asubuhi, hujambo?"}
], "meta": {"source_id": "greeting", "tgt_lang": "Swahili", "rating": "good", "score": 0.93, "domain": "conversations", "category": "greeting"}}
```

### Training data - input/output pairs (`<run>.pairs.jsonl`)

A simpler, framework-agnostic shape (seq2seq, scripts, custom loaders):

```json
{"input": "Good morning, how are you?", "output": "Habari za asubuhi, hujambo?", "src_lang": "English", "tgt_lang": "Swahili", "meta": {"source_id": "greeting", "rating": "good", "score": 0.93}}
```

### Full table (`<run>.csv`)

Every translation (kept regardless of rating), one row each. Columns:

```
source_id, speaker, category, src_lang, tgt_lang, source_text, translation,
confidence, aggregate_score, rating, ok, model, error,
eval:confidence, eval:back_translation, eval:llm_judge, judge_adequacy, judge_fluency
```

The `eval:*` and `judge_*` columns appear when those evaluators ran.

### Report (`<run>.report.json` / `.report.md`)

The score summary: `total`, `ok`, `avg_score`, `lowest_score`,
`rating_counts`, and `by_signal` / `by_language` / `by_speaker` breakdowns, plus
a `verdict`. See [`evals.md`](evals.md) for what the scores and ratings mean.

---

## Choosing data for training

- Use **`--min-rating good`** for a strict, high-trust fine-tuning set;
  **`marginal`** (default) to keep more data with human review of the borderline
  rows.
- The CSV is the place to **audit** before training - sort by `aggregate_score`,
  inspect `eval:back_translation` vs `judge_*` disagreements, and spot-check the
  risky rows.
- Everything also lands in SQLite, so runs accumulate into a reusable corpus
  (`tafsiri runs`, `tafsiri report <id>`).
