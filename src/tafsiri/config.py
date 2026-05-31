"""Configuration and environment loading.

Reads from environment / .env. Kept tiny and side-effect-light so other
modules don't each reach into os.environ.
"""

from __future__ import annotations

import os
from dataclasses import dataclass

from dotenv import load_dotenv

load_dotenv()

DEFAULT_BASE_URL = "https://api.daraja.ai/v1"
DEFAULT_SOURCE_LANG = "English"
# Languages bundled with the example emergency dataset.
DEFAULT_TARGET_LANGUAGES = ["Swahili", "Yoruba", "Amharic", "Creole"]


def get_api_key() -> str | None:
    """Daraja AI key from DARAJA_API_KEY. Trailing slash/whitespace stripped
    (a common copy-paste artifact)."""
    key = os.environ.get("DARAJA_API_KEY")
    if key:
        key = key.strip().rstrip("/")
    return key or None


@dataclass
class Settings:
    api_key: str | None = None
    base_url: str = DEFAULT_BASE_URL
    source_lang: str = DEFAULT_SOURCE_LANG
    request_timeout: float = 30.0
    request_delay: float = 0.2        # politeness sleep between calls

    @classmethod
    def from_env(cls) -> "Settings":
        return cls(api_key=get_api_key())
