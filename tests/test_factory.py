import pytest

from tafsiri.providers import DarajaTranslator, LLMTranslator, build_translator
from tafsiri.schema import Translation

from conftest import FakeChatModel


def test_build_daraja_engine():
    t = build_translator("daraja", daraja_key="dk_test")
    assert isinstance(t, DarajaTranslator)


def test_daraja_requires_key():
    with pytest.raises(ValueError, match="DARAJA_API_KEY"):
        build_translator("daraja", daraja_key=None)


def test_unknown_engine():
    with pytest.raises(ValueError, match="unknown engine"):
        build_translator("magic")


def test_llm_engine_spec_must_have_provider_and_model():
    with pytest.raises(ValueError, match="llm:<provider>:<model>"):
        build_translator("llm:openai")  # missing model


def test_llm_translator_translates():
    t = LLMTranslator(FakeChatModel("habari dunia"), name="llm:fake")
    tr = t.translate("hello world", "English", "Swahili")
    assert tr.ok
    assert tr.text == "habari dunia"
    assert tr.confidence is None      # LLMs have no native confidence
    assert tr.model == "llm:fake"


def test_llm_translator_strips_whitespace():
    t = LLMTranslator(FakeChatModel("  habari  \n"))
    assert t.translate("hi", "English", "Swahili").text == "habari"


def test_llm_translator_empty_output_is_failure():
    t = LLMTranslator(FakeChatModel("   "))
    tr = t.translate("hi", "English", "Swahili")
    assert not tr.ok
    assert "empty" in tr.error


def test_llm_translator_handles_exception():
    class Boom:
        def invoke(self, _):
            raise RuntimeError("model offline")

    tr = LLMTranslator(Boom()).translate("hi", "English", "Swahili")
    assert not tr.ok
    assert "model offline" in tr.error
