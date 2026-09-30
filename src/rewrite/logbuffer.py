"""In-memory log buffer shared by the pipeline and the log viewers."""

from __future__ import annotations

import contextlib
import threading
from collections import deque
from collections.abc import Callable
from datetime import datetime

_MAX_ENTRIES = 200


class LogBuffer:
    """Thread-safe ring buffer of timestamped log messages."""

    def __init__(self, maxlen: int = _MAX_ENTRIES) -> None:
        self._entries: deque[tuple[datetime, str]] = deque(maxlen=maxlen)
        self._lock = threading.Lock()
        self._listeners: list[Callable[[datetime, str], None]] = []

    def append(self, message: str) -> None:
        now = datetime.now()
        with self._lock:
            self._entries.append((now, message))
        for cb in self._listeners:
            with contextlib.suppress(Exception):
                cb(now, message)

    def snapshot(self) -> list[tuple[datetime, str]]:
        with self._lock:
            return list(self._entries)

    def on_entry(self, callback: callable) -> None:
        self._listeners.append(callback)

    def remove_listener(self, callback: callable) -> None:
        with contextlib.suppress(ValueError):
            self._listeners.remove(callback)


# Singleton shared across the app.
log_buffer = LogBuffer()
