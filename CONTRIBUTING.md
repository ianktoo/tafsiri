# Contributing to tafsiri

Thanks for your interest! `tafsiri` is built around clean seams, so most
contributions slot into one place.

## Setup

```bash
uv sync --extra dev
uv run pytest        # network-free; providers and the LLM judge are faked
```

## Where things go (one concern per module)

- **New translation backend?** Implement the `Translator` protocol in
  `providers/` (see `providers/daraja.py`). Never raise on a failed call —
  return a `Translation` with `ok=False`.
- **New quality signal?** Implement the `Evaluator` protocol in `evaluators/`.
  Return an `EvalSignal` with a 0..1 score (or `None` when not applicable).
- **New output destination?** Implement the `Sink` protocol in `storage.py`
  (e.g. a `ghost.build` sink alongside `SQLiteStore`).
- **New dataset?** Add JSONL/CSV under `data/source/` — the loader is
  domain-agnostic; only `text` is required.

## Pull requests

1. Add or update tests (keep them network-free — fake the provider/judge).
2. Run `uv run pytest` and make sure it's green.
3. Keep changes focused and explain the "why" in the PR description.

## Code style

Match the surrounding code: type hints, small focused functions, and
docstrings that explain intent rather than restating the code.
