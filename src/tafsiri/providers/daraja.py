"""Daraja AI (Babel) translation backend.

Wraps POST {base_url}/translate. Never raises on a failed call — returns a
Translation with ok=False so batch runs survive transient errors.
"""

from __future__ import annotations

import time
from typing import Callable

import requests

from tafsiri.config import DEFAULT_BASE_URL
from tafsiri.schema import Translation

# Status codes worth retrying: rate limiting + transient server errors.
_RETRYABLE = {429, 500, 502, 503, 504}


class DarajaTranslator:
    name = "daraja-babel"

    def __init__(self, api_key: str, base_url: str = DEFAULT_BASE_URL,
                 timeout: float = 30.0, session: requests.Session | None = None,
                 max_retries: int = 4, backoff_base: float = 1.0,
                 sleep: Callable[[float], None] = time.sleep):
        if not api_key:
            raise ValueError("DarajaTranslator requires an API key")
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self._session = session or requests.Session()
        self.max_retries = max_retries
        self.backoff_base = backoff_base
        self._sleep = sleep

    @property
    def _url(self) -> str:
        return f"{self.base_url}/translate"

    @staticmethod
    def _error_message(status: int, src_lang: str, tgt_lang: str, data: object) -> str:
        """Turn a failed response body into a readable error.

        Daraja reports failures with a JSON ``message`` field — surface that
        instead of dumping the raw dict. An unsupported language pair (HTTP 400)
        gets a pair-specific message so the cause is obvious in batch logs.
        """
        msg = data.get("message") if isinstance(data, dict) else None
        if status == 400 and msg and "language" in msg.lower():
            return f"unsupported language pair {src_lang!r} -> {tgt_lang!r}: {msg} (HTTP 400)"
        if msg:
            return f"HTTP {status}: {msg}"
        return f"HTTP {status}: {data}"

    def _retry_after(self, resp: requests.Response, attempt: int) -> float:
        """Honor a Retry-After header if present, else exponential backoff."""
        header = resp.headers.get("Retry-After")
        if header:
            try:
                return max(0.0, float(header))
            except ValueError:
                pass
        return self.backoff_base * (2 ** attempt)

    def translate(self, text: str, src_lang: str, tgt_lang: str) -> Translation:
        out = Translation(src_lang=src_lang, tgt_lang=tgt_lang)
        resp = None
        for attempt in range(self.max_retries + 1):
            try:
                resp = self._session.post(
                    self._url,
                    headers={
                        "Authorization": f"Bearer {self.api_key}",
                        "Content-Type": "application/json",
                    },
                    json={"text": text, "from": src_lang, "to": tgt_lang},
                    timeout=self.timeout,
                )
            except requests.RequestException as e:
                if attempt < self.max_retries:
                    self._sleep(self.backoff_base * (2 ** attempt))
                    continue
                out.error = f"request failed: {e}"
                return out

            if resp.status_code in _RETRYABLE and attempt < self.max_retries:
                self._sleep(self._retry_after(resp, attempt))
                continue
            break

        try:
            data = resp.json()
        except ValueError:
            out.error = f"HTTP {resp.status_code}: non-JSON response: {resp.text[:200]}"
            return out

        out.raw = data
        if not resp.ok:
            out.error = self._error_message(resp.status_code, src_lang, tgt_lang, data)
            return out

        out.text = data.get("translation")
        out.confidence = data.get("confidence")
        out.model = data.get("model")
        out.ok = out.text is not None
        if not out.ok:
            out.error = f"no translation field in response: {data}"
        return out
