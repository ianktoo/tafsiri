"""LLM-as-judge evaluator — provider-agnostic via LangChain.

The judge is any LangChain ``BaseChatModel``: OpenAI, Anthropic, or a local
Ollama model. It rates the translation on adequacy (meaning preserved) and
fluency (natural in the target language), 1..5 each, and we normalize the mean
to 0..1.

LangChain is an optional dependency (``pip install 'tafsiri[judge]'``; add
``[ollama]`` for local models). Nothing here imports LangChain at module load —
imports are lazy so the rest of the package works without it.
"""

from __future__ import annotations

import json
import re
from typing import Any

from tafsiri.schema import EvalSignal, SourceRecord, Translation

_JUDGE_SYSTEM = (
    "You are a strict bilingual translation evaluator. Given a source sentence "
    "and its translation into a target language, rate the translation on two "
    "axes, each an integer from 1 (terrible) to 5 (perfect):\n"
    "  - adequacy: is the full meaning preserved, with nothing added or lost?\n"
    "  - fluency: is it natural, grammatical text in the target language?\n"
    "For safety-critical (emergency/medical) text, penalize any change in "
    "meaning harshly. Respond with ONLY a compact JSON object: "
    '{"adequacy": <int>, "fluency": <int>, "reason": "<short>"}.'
)

_JSON_RE = re.compile(r"\{.*\}", re.DOTALL)


def make_chat_model(spec: str, **kwargs: Any):
    """Build a LangChain chat model from a ``provider:model`` spec.

    Examples: ``"ollama:llama3.1"``, ``"openai:gpt-4o-mini"``,
    ``"anthropic:claude-sonnet-4-6"``. Local Ollama is handled explicitly so it
    works without provider API keys.
    """
    provider, _, model = spec.partition(":")
    if not model:
        raise ValueError(f"judge spec must be 'provider:model', got {spec!r}")

    if provider == "ollama":
        try:
            from langchain_ollama import ChatOllama
        except ImportError as e:
            raise ImportError(
                "Ollama judge needs langchain-ollama: pip install 'tafsiri[judge,ollama]' "
                "(and a running Ollama server)."
            ) from e
        return ChatOllama(model=model, temperature=0, **kwargs)

    try:
        from langchain.chat_models import init_chat_model
    except ImportError as e:
        raise ImportError(
            "LLM judge needs LangChain: pip install 'tafsiri[judge]' "
            "plus the provider integration (e.g. langchain-openai)."
        ) from e
    return init_chat_model(model, model_provider=provider, temperature=0, **kwargs)


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

    def __init__(self, model: Any):
        """``model`` is a LangChain BaseChatModel (or anything with .invoke()
        returning an object with .content). Build one via make_chat_model()."""
        self.model = model

    def evaluate(self, source: SourceRecord, translation: Translation) -> EvalSignal:
        if not translation.ok or not translation.text:
            return EvalSignal(self.name, None, {"reason": "no translation to judge"})

        prompt = (
            f"Source language: {translation.src_lang}\n"
            f"Target language: {translation.tgt_lang}\n"
            f"Source: {source.text}\n"
            f"Translation: {translation.text}"
        )
        try:
            resp = self.model.invoke(
                [("system", _JUDGE_SYSTEM), ("human", prompt)])
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
