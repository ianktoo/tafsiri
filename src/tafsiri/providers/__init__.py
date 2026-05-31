"""Translation backends (the *generation* concern).

A provider implements the ``Translator`` protocol. Swap providers without
touching the rest of the pipeline.
"""

from tafsiri.providers.base import Translator
from tafsiri.providers.daraja import DarajaTranslator

__all__ = ["Translator", "DarajaTranslator"]
