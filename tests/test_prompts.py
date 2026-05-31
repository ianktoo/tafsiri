import pytest

from tafsiri.evaluators.llm_judge import make_chat_model, resolve_spec
from tafsiri.prompts import JUDGE_SYSTEM, build_judge_user


def test_judge_prompt_is_importable_and_nonempty():
    assert isinstance(JUDGE_SYSTEM, str) and "adequacy" in JUDGE_SYSTEM


def test_build_judge_user_includes_all_fields():
    out = build_judge_user("hello", "English", "Swahili", "habari")
    assert "English" in out and "Swahili" in out
    assert "hello" in out and "habari" in out


def test_resolve_spec_aliases():
    assert resolve_spec("claude:claude-sonnet-4-6") == ("anthropic", "claude-sonnet-4-6")
    assert resolve_spec("gemini:gemini-2.0-flash") == ("google_genai", "gemini-2.0-flash")
    assert resolve_spec("gpt:gpt-4o-mini") == ("openai", "gpt-4o-mini")
    assert resolve_spec("openai:gpt-4o") == ("openai", "gpt-4o")
    assert resolve_spec("ollama:llama3.1") == ("ollama", "llama3.1")


def test_resolve_spec_requires_model():
    with pytest.raises(ValueError, match="provider:model"):
        resolve_spec("openai")


def test_make_chat_model_missing_dep_gives_helpful_error():
    # LangChain is not installed in the test env -> informative ImportError
    with pytest.raises(ImportError, match="LangChain|langchain"):
        make_chat_model("openai:gpt-4o-mini")
