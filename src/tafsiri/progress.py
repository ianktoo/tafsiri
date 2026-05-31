"""A tiny dependency-free progress renderer for batch runs.

Draws a single self-updating line — spinner, bar, counts, and a rotating status
of the item in flight — using carriage returns. It only animates on a TTY; when
output is piped/redirected (not a terminal) it becomes a no-op so logs stay
clean. No third-party deps (no rich/tqdm).
"""

from __future__ import annotations

import shutil
import sys
from typing import TextIO

_FRAMES = "⠋⠙⠹⠸⠼⠴⠦⠧⠇⠏"


class Progress:
    def __init__(self, total: int, enabled: bool = True,
                 stream: TextIO | None = None, bar_width: int = 22):
        self.total = max(0, total)
        self.done = 0
        self.ok = 0
        self.failed = 0
        self.stream = stream or sys.stdout
        is_tty = getattr(self.stream, "isatty", lambda: False)()
        self.enabled = bool(enabled and is_tty and self.total > 0)
        self.bar_width = bar_width
        self._frame = 0
        self._last_len = 0

    def _term_width(self) -> int:
        try:
            return shutil.get_terminal_size().columns
        except Exception:
            return 80

    def update(self, label: str = "", ok: bool = True) -> None:
        """Record one finished item and redraw."""
        self.done += 1
        if ok:
            self.ok += 1
        else:
            self.failed += 1
        self._render(label)

    def _render(self, label: str) -> None:
        if not self.enabled:
            return
        self._frame = (self._frame + 1) % len(_FRAMES)
        frac = self.done / self.total if self.total else 1.0
        filled = int(self.bar_width * frac)
        bar = "█" * filled + "░" * (self.bar_width - filled)
        line = (f"{_FRAMES[self._frame]} [{bar}] {self.done}/{self.total} "
                f"{int(frac * 100):3d}%  ✓{self.ok} ✗{self.failed}  {label}")
        line = line[: max(0, self._term_width() - 1)]   # avoid wrapping
        pad = max(0, self._last_len - len(line))
        self.stream.write("\r" + line + " " * pad)
        self.stream.flush()
        self._last_len = len(line)

    def note(self, message: str) -> None:
        """Print a message on its own line, above the progress bar."""
        self._clear()
        print(message)

    def finish(self) -> None:
        """Erase the progress line so following output starts clean."""
        self._clear()

    def _clear(self) -> None:
        if self.enabled and self._last_len:
            self.stream.write("\r" + " " * self._last_len + "\r")
            self.stream.flush()
        self._last_len = 0
