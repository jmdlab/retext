"""In-memory log buffer and tkinter log viewer window."""

from __future__ import annotations

import contextlib
import threading
import tkinter as tk
from collections import deque
from datetime import datetime
from pathlib import Path
from tkinter import ttk
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    pass

_MAX_ENTRIES = 200


class LogBuffer:
    """Thread-safe ring buffer of timestamped log messages."""

    def __init__(self, maxlen: int = _MAX_ENTRIES) -> None:
        self._entries: deque[tuple[datetime, str]] = deque(maxlen=maxlen)
        self._lock = threading.Lock()
        self._listeners: list[callable] = []

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


class LogViewer:
    """Tkinter window that displays the log buffer."""

    def __init__(self, icon_path: Path | None = None) -> None:
        self._window: tk.Toplevel | tk.Tk | None = None
        self._text: tk.Text | None = None
        self._icon_path = icon_path

    @property
    def is_open(self) -> bool:
        return self._window is not None

    def show(self) -> None:
        if self._window is not None:
            self._window.lift()
            self._window.focus_force()
            return

        self._window = tk.Toplevel() if tk._default_root else tk.Tk()
        self._window.title("Retext \u2014 Log")
        self._window.geometry("520x360")
        self._window.minsize(360, 200)
        self._window.protocol("WM_DELETE_WINDOW", self._on_close)

        if self._icon_path and self._icon_path.exists():
            with contextlib.suppress(tk.TclError):
                self._window.iconbitmap(str(self._icon_path))

        frame = ttk.Frame(self._window, padding=8)
        frame.pack(fill="both", expand=True)

        # Scrollable text area
        self._text = tk.Text(
            frame,
            wrap="word",
            state="disabled",
            font=("Consolas", 9),
            bg="#1e1e1e",
            fg="#cccccc",
            insertbackground="#cccccc",
            selectbackground="#264f78",
            borderwidth=0,
            padx=8,
            pady=8,
        )
        scrollbar = ttk.Scrollbar(frame, command=self._text.yview)
        self._text.configure(yscrollcommand=scrollbar.set)
        scrollbar.pack(side="right", fill="y")
        self._text.pack(side="left", fill="both", expand=True)

        # Tag for timestamps
        self._text.tag_configure("ts", foreground="#6a9955")
        self._text.tag_configure("error", foreground="#f44747")
        self._text.tag_configure("success", foreground="#4ec9b0")
        self._text.tag_configure("info", foreground="#cccccc")

        # Load existing entries
        for ts, msg in log_buffer.snapshot():
            self._insert_entry(ts, msg)

        # Listen for new entries
        log_buffer.on_entry(self._on_new_entry)

        self._window.mainloop()

    def _insert_entry(self, ts: datetime, msg: str) -> None:
        if self._text is None:
            return
        self._text.configure(state="normal")
        ts_str = ts.strftime("%H:%M:%S")
        self._text.insert("end", f"{ts_str}  ", "ts")
        tag = "info"
        msg_lower = msg.lower()
        if "error" in msg_lower or "failed" in msg_lower:
            tag = "error"
        elif "done" in msg_lower or "replaced" in msg_lower:
            tag = "success"
        self._text.insert("end", f"{msg}\n", tag)
        self._text.configure(state="disabled")
        self._text.see("end")

    def _on_new_entry(self, ts: datetime, msg: str) -> None:
        if self._window is None:
            return
        # Schedule on the Tk main thread
        with contextlib.suppress(Exception):
            self._window.after(0, self._insert_entry, ts, msg)

    def _on_close(self) -> None:
        log_buffer.remove_listener(self._on_new_entry)
        if self._window is not None:
            self._window.quit()
            self._window.destroy()
            self._window = None
            self._text = None
