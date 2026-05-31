"""Configuration and environment loading.

Reads from environment / .env. Kept tiny and side-effect-light so other
modules don't each reach into os.environ.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

DEFAULT_BASE_URL = "https://api.daraja.ai/v1"
DEFAULT_SOURCE_LANG = "English"
# Languages bundled with the example emergency dataset.
DEFAULT_TARGET_LANGUAGES = ["Swahili", "Yoruba", "Amharic", "Creole"]


def data_home() -> Path:
    """Where tafsiri keeps its db and outputs by default.

    A single per-user location (``~/.tafsiri``) so results don't scatter across
    whatever directory you happen to run from, and it works the same on Linux,
    macOS, and Windows. Override with the ``TAFSIRI_HOME`` env var, or per-run
    with ``--db`` / ``--out-dir``.
    """
    env = os.environ.get("TAFSIRI_HOME")
    return Path(env) if env else Path.home() / ".tafsiri"


def default_db_path() -> str:
    return str(data_home() / "tafsiri.db")


def default_out_dir() -> str:
    return str(data_home() / "out")


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
