"""LLM-based translation engine.

Uses a general-purpose chat model (via LangChain) to translate. This is mainly
a *research baseline*: it lets you compare a purpose-built engine (e.g. Daraja's
Babel) against general LLMs on the same eval harness, for the same African
languages.

Caveats worth knowing:
  - General LLMs have no native translation confidence, so ``confidence`` is
    None — lean on the back-translation and LLM-judge evaluators for scoring.
  - Quality on low-resource African languages varies a lot by model; that gap
    is exactly what this repo is built to measure.

LangChain is optional — install a provider extra (openai/anthropic/gemini/ollama).
"""

from __future__ import annotations

from typing import Any, Callable, Optional

from tafsiri.prompts import TRANSLATE_SYSTEM, build_translate_user
from tafsiri.schema import Translation


class LLMTranslator:
    def __init__(self, model: Any, name: str = "llm",
                 system_prompt: Optional[str] = None,
                 user_builder: Optional[Callable[[str, str, str], str]] = None):
        """``model`` is a LangChain chat model (build via make_chat_model())."""
        self.model = model
        self.name = name
        self.system_prompt = system_prompt or TRANSLATE_SYSTEM
        self.user_builder = user_builder or build_translate_user

    def translate(self, text: str, src_lang: str, tgt_lang: str) -> Translation:
        out = Translation(src_lang=src_lang, tgt_lang=tgt_lang)
        prompt = self.user_builder(text, src_lang, tgt_lang)
        try:
            resp = self.model.invoke(
                [("system", self.system_prompt), ("human", prompt)])
            content = getattr(resp, "content", resp)
        except Exception as e:  # never crash a batch
            out.error = f"llm translate failed: {e}"
            return out

        translated = (content if isinstance(content, str) else str(content)).strip()
        if not translated:
            out.error = "empty translation from model"
            return out

        out.text = translated
        out.model = self.name
        out.confidence = None   # general LLMs don't return a calibrated score
        out.ok = True
        return out
