"""Translation backends (the *generation* concern).

A provider implements the ``Translator`` protocol. Engines are swappable: build
one from an ``--engine`` spec via ``build_translator``, or instantiate directly.
"""

from tafsiri.providers.base import Translator
from tafsiri.providers.daraja import DarajaTranslator
from tafsiri.providers.factory import ENGINES, build_translator
from tafsiri.providers.llm import LLMTranslator

__all__ = [
    "Translator",
    "DarajaTranslator",
    "LLMTranslator",
    "build_translator",
    "ENGINES",
]
