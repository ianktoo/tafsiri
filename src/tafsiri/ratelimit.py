"""Shared rate limiting for concurrent runs.

When several worker threads call a provider at once, a single shared limiter
keeps the *global* request rate within bounds — so concurrency speeds up
wall-clock time (overlapping network waits) without hammering the API.

``RateLimitedTranslator`` wraps any ``Translator`` so EVERY call it makes —
including back-translation round-trips — passes through the same limiter.
This module is a thin decorator layer; it adds no translation logic of its own.
"""

from __future__ import annotations

import threading
import time
from typing import Callable

from tafsiri.schema import Translation


class RateLimiter:
    """Token-spacing limiter: grants are spaced at least ``min_interval`` apart,
    across all threads. Thread-safe. ``min_interval`` <= 0 disables it."""

    def __init__(self, min_interval: float,
                 sleep: Callable[[float], None] = time.sleep,
                 clock: Callable[[], float] = time.monotonic):
        self.min_interval = max(0.0, min_interval)
        self._lock = threading.Lock()
        self._next = 0.0
        self._sleep = sleep
        self._clock = clock

    def acquire(self) -> None:
        if self.min_interval <= 0:
            return
        with self._lock:
            now = self._clock()
            start = now if now >= self._next else self._next
            self._next = start + self.min_interval
            wait = start - now
        if wait > 0:
            self._sleep(wait)


class RateLimitedTranslator:
    """Wraps a Translator so each ``translate`` acquires a slot first."""

    def __init__(self, inner, limiter: RateLimiter):
        self.inner = inner
        self.limiter = limiter
        self.name = getattr(inner, "name", "ratelimited")

    def translate(self, text: str, src_lang: str, tgt_lang: str) -> Translation:
        self.limiter.acquire()
        return self.inner.translate(text, src_lang, tgt_lang)
