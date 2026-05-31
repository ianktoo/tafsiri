"""The Translator protocol — the only contract a translation backend must meet."""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from tafsiri.schema import Translation


@runtime_checkable
class Translator(Protocol):
    """Anything that turns text in one language into another.

    Implementations must never raise on a failed translation — they return a
    ``Translation`` with ``ok=False`` and a populated ``error`` instead, so the
    pipeline can record failures rather than crash mid-batch.
    """

    name: str

    def translate(self, text: str, src_lang: str, tgt_lang: str) -> Translation:
        ...
