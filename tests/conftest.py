"""Shared test fixtures and fakes — everything here is network-free."""

from __future__ import annotations

import pytest

from tafsiri.schema import SourceRecord, Translation


class FakeTranslator:
    """Deterministic translator for tests. Returns a canned mapping, or a
    reversible 'pseudo-translation' so back-translation round-trips cleanly."""

    name = "fake"

    def __init__(self, mapping=None, confidence=0.9, fail_for=None):
        self.mapping = mapping or {}
        self.confidence = confidence
        self.fail_for = set(fail_for or [])
        self.calls = []

    def translate(self, text: str, src_lang: str, tgt_lang: str) -> Translation:
        self.calls.append((text, src_lang, tgt_lang))
        if text in self.fail_for:
            return Translation(src_lang=src_lang, tgt_lang=tgt_lang,
                               ok=False, error="forced failure")
        out = self.mapping.get((text, tgt_lang), f"[{tgt_lang}] {text}")
        return Translation(src_lang=src_lang, tgt_lang=tgt_lang, text=out,
                           confidence=self.confidence, model="fake-v1", ok=True)


class EchoBackTranslator:
    """Translates X->Y as '<<text>>' and back Y->X to the original text, so a
    perfect round-trip scores 1.0."""

    name = "echo"

    def translate(self, text: str, src_lang: str, tgt_lang: str) -> Translation:
        if text.startswith("<<") and text.endswith(">>"):
            restored = text[2:-2]
            return Translation(src_lang=src_lang, tgt_lang=tgt_lang,
                               text=restored, confidence=0.9, ok=True)
        return Translation(src_lang=src_lang, tgt_lang=tgt_lang,
                           text=f"<<{text}>>", confidence=0.9, ok=True)


class FakeChatModel:
    """Stand-in for a LangChain chat model: .invoke(messages) -> obj with
    .content. ``content`` may be a fixed string or a callable(messages)->str."""

    def __init__(self, content):
        self._content = content

    def invoke(self, messages):
        text = self._content(messages) if callable(self._content) else self._content

        class _Resp:
            pass

        r = _Resp()
        r.content = text
        return r


@pytest.fixture
def source():
    return SourceRecord(id="s1", text="hello world", src_lang="English",
                        meta={"speaker": "affected_party", "category": "medical"})


@pytest.fixture
def ok_translation():
    return Translation(src_lang="English", tgt_lang="Swahili", text="habari dunia",
                       confidence=0.8, model="babel", ok=True)
