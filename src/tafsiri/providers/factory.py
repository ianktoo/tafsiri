"""Swappable translation engines — build a Translator from an ``--engine`` spec.

Engine specs:
  - ``daraja``                       Daraja AI / Babel (default; uses DARAJA_API_KEY)
  - ``llm:<provider>:<model>``       any LangChain chat model as a translator,
                                     e.g. ``llm:claude:claude-sonnet-4-6``,
                                     ``llm:openai:gpt-4o-mini``, ``llm:ollama:llama3.1``

Add your own engine by writing a class that satisfies the ``Translator``
protocol and extending ``build_translator`` (or registering it here).
"""

from __future__ import annotations

from tafsiri.config import DEFAULT_BASE_URL
from tafsiri.providers.base import Translator
from tafsiri.providers.daraja import DarajaTranslator
from tafsiri.providers.llm import LLMTranslator

# Names recognized by the CLI / docs (the `llm:` family is dynamic).
ENGINES = ("daraja", "llm:<provider>:<model>")


def build_translator(spec: str, *, daraja_key: str | None = None,
                     base_url: str = DEFAULT_BASE_URL,
                     timeout: float = 30.0) -> Translator:
    spec = (spec or "daraja").strip()

    if spec == "daraja":
        if not daraja_key:
            raise ValueError("the 'daraja' engine needs DARAJA_API_KEY")
        return DarajaTranslator(daraja_key, base_url=base_url, timeout=timeout)

    if spec.startswith("llm:"):
        model_spec = spec[len("llm:"):]
        if not model_spec or ":" not in model_spec:
            raise ValueError(
                "llm engine spec must be 'llm:<provider>:<model>', "
                f"e.g. llm:claude:claude-sonnet-4-6 — got {spec!r}")
        # Imported lazily: LangChain is an optional dependency.
        from tafsiri.evaluators.llm_judge import make_chat_model
        return LLMTranslator(make_chat_model(model_spec), name=f"llm:{model_spec}")

    raise ValueError(
        f"unknown engine {spec!r}. Use 'daraja' or 'llm:<provider>:<model>'.")
