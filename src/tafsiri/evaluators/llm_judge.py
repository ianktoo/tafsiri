"""LLM-as-judge evaluator — provider-agnostic via LangChain.

The judge is any LangChain ``BaseChatModel``: hosted (OpenAI, Anthropic/Claude,
Google/Gemini) or local (Ollama). It rates the translation on adequacy (meaning
preserved) and fluency (natural in the target language), 1..5 each; we normalize
the mean to 0..1.

LangChain is an optional dependency. Install the integration you want:
    pip install 'tafsiri[openai]'      # OpenAI
    pip install 'tafsiri[anthropic]'   # Claude
    pip install 'tafsiri[gemini]'      # Gemini
    pip install 'tafsiri[ollama]'      # local Ollama
Nothing here imports LangChain at module load — imports are lazy so the rest of
the package works without it.

Prompts live in ``tafsiri.prompts`` and can be overridden per evaluator.
"""

from __future__ import annotations

import json
import re
from typing import Any, Callable, Optional

from tafsiri.prompts import JUDGE_SYSTEM, build_judge_user
from tafsiri.schema import EvalSignal, SourceRecord, Translation

_JSON_RE = re.compile(r"\{.*\}", re.DOTALL)

# Friendly aliases -> LangChain ``model_provider`` names.
_PROVIDER_ALIASES = {
    "claude": "anthropic",
    "gemini": "google_genai",
    "google": "google_genai",
    "gpt": "openai",
}

# Provider -> the pip extra / integration package that supplies it.
_PROVIDER_PACKAGES = {
    "openai": "langchain-openai ( tafsiri[openai] )",
    "anthropic": "langchain-anthropic ( tafsiri[anthropic] )",
    "google_genai": "langchain-google-genai ( tafsiri[gemini] )",
}


def resolve_spec(spec: str) -> tuple[str, str]:
    """Split a ``provider:model`` spec and normalize provider aliases.

    >>> resolve_spec("claude:claude-sonnet-4-6")
    ('anthropic', 'claude-sonnet-4-6')
    >>> resolve_spec("gemini:gemini-2.0-flash")
    ('google_genai', 'gemini-2.0-flash')
    """
    provider, _, model = spec.partition(":")
    if not model:
        raise ValueError(f"judge spec must be 'provider:model', got {spec!r}")
    provider = _PROVIDER_ALIASES.get(provider, provider)
    return provider, model


def make_chat_model(spec: str, **kwargs: Any):
    """Build a LangChain chat model from a ``provider:model`` spec.

    Examples: ``"ollama:llama3.1"``, ``"openai:gpt-4o-mini"``,
    ``"claude:claude-sonnet-4-6"``, ``"gemini:gemini-2.0-flash"``.
    """
    provider, model = resolve_spec(spec)

    if provider == "ollama":
        try:
            from langchain_ollama import ChatOllama
        except ImportError as e:
            raise ImportError(
                "Ollama judge needs langchain-ollama: pip install "
                "'tafsiri[ollama]' (and a running Ollama server)."
            ) from e
        return ChatOllama(model=model, temperature=0, **kwargs)

    try:
        from langchain.chat_models import init_chat_model
    except ImportError as e:
        raise ImportError(
            "LLM judge needs LangChain: pip install 'tafsiri[judge]' plus the "
            "provider integration (e.g. tafsiri[openai|anthropic|gemini])."
        ) from e

    try:
        return init_chat_model(model, model_provider=provider, temperature=0, **kwargs)
    except ImportError as e:
        pkg = _PROVIDER_PACKAGES.get(provider, f"the {provider} integration")
        raise ImportError(
            f"Judge provider {provider!r} needs {pkg}. Install it and retry."
        ) from e


def _parse_scores(content: str) -> dict | None:
    match = _JSON_RE.search(content or "")
    if not match:
        return None
    try:
        return json.loads(match.group(0))
    except json.JSONDecodeError:
        return None


class LLMJudgeEvaluator:
    name = "llm_judge"

    def __init__(self, model: Any, system_prompt: Optional[str] = None,
                 user_builder: Optional[Callable[[str, str, str, str], str]] = None):
        """``model`` is a LangChain chat model (build one via make_chat_model()).

        ``system_prompt`` and ``user_builder`` override the defaults from
        ``tafsiri.prompts`` for custom rubrics."""
        self.model = model
        self.system_prompt = system_prompt or JUDGE_SYSTEM
        self.user_builder = user_builder or build_judge_user

    def evaluate(self, source: SourceRecord, translation: Translation) -> EvalSignal:
        if not translation.ok or not translation.text:
            return EvalSignal(self.name, None, {"reason": "no translation to judge"})

        prompt = self.user_builder(source.text, translation.src_lang,
                                   translation.tgt_lang, translation.text)
        try:
            resp = self.model.invoke(
                [("system", self.system_prompt), ("human", prompt)])
            content = getattr(resp, "content", resp)
        except Exception as e:  # provider/network errors shouldn't kill the batch
            return EvalSignal(self.name, None, {"reason": "judge call failed", "error": str(e)})

        scores = _parse_scores(content if isinstance(content, str) else str(content))
        if not scores or "adequacy" not in scores or "fluency" not in scores:
            return EvalSignal(self.name, None,
                              {"reason": "could not parse judge output", "raw": str(content)[:300]})

        try:
            adequacy = float(scores["adequacy"])
            fluency = float(scores["fluency"])
        except (TypeError, ValueError):
            return EvalSignal(self.name, None, {"reason": "non-numeric scores", "raw": scores})

        mean = (adequacy + fluency) / 2.0
        normalized = max(0.0, min(1.0, (mean - 1.0) / 4.0))   # 1..5 -> 0..1
        return EvalSignal(self.name, normalized, {
            "adequacy": adequacy, "fluency": fluency,
            "reason": scores.get("reason", ""),
        })
