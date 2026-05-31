"""Load source text to translate — domain-agnostic.

Accepts JSONL or CSV. Recognized columns/keys: ``id``, ``text`` (required),
``src_lang``/``lang``. Every other field is preserved in ``SourceRecord.meta``
so domain extras (speaker, category, ...) survive end to end.
"""

from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Iterable

from tafsiri.config import DEFAULT_SOURCE_LANG
from tafsiri.schema import SourceRecord

_TEXT_KEYS = ("text", "source_text", "input")
_LANG_KEYS = ("src_lang", "source_lang", "lang", "from")


def _pick(d: dict, keys: Iterable[str]) -> str | None:
    for k in keys:
        if k in d and d[k] not in (None, ""):
            return str(d[k])
    return None


def _record_from_dict(d: dict, index: int, default_lang: str) -> SourceRecord:
    text = _pick(d, _TEXT_KEYS)
    if text is None:
        raise ValueError(
            f"row {index}: missing text (expected one of {_TEXT_KEYS})")
    rid = str(d.get("id") or f"row-{index}")
    src_lang = _pick(d, _LANG_KEYS) or default_lang
    consumed = {"id", *(_TEXT_KEYS), *(_LANG_KEYS)}
    meta = {k: v for k, v in d.items() if k not in consumed}
    return SourceRecord(id=rid, text=text, src_lang=src_lang, meta=meta)


def load_jsonl(path: str | Path, default_lang: str = DEFAULT_SOURCE_LANG) -> list[SourceRecord]:
    records: list[SourceRecord] = []
    with Path(path).open(encoding="utf-8") as f:
        for i, line in enumerate(f):
            line = line.strip()
            if not line:
                continue
            records.append(_record_from_dict(json.loads(line), i, default_lang))
    return records


def load_csv(path: str | Path, default_lang: str = DEFAULT_SOURCE_LANG) -> list[SourceRecord]:
    with Path(path).open(newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        return [_record_from_dict(row, i, default_lang)
                for i, row in enumerate(reader)]


def load_source(path: str | Path, default_lang: str = DEFAULT_SOURCE_LANG) -> list[SourceRecord]:
    """Dispatch by file extension (.jsonl/.json -> JSONL, .csv -> CSV)."""
    suffix = Path(path).suffix.lower()
    if suffix in (".jsonl", ".json", ".ndjson"):
        return load_jsonl(path, default_lang)
    if suffix == ".csv":
        return load_csv(path, default_lang)
    raise ValueError(f"unsupported source format: {suffix!r} (use .jsonl or .csv)")
