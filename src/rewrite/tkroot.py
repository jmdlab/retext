"""Singleton hidden Tk root — ensures only one Tk() instance exists."""

from __future__ import annotations

import threading
import tkinter as tk

from rewrite.ui import apply_theme, enable_dpi_awareness

_lock = threading.Lock()
_root: tk.Tk | None = None


def get_root() -> tk.Tk:
    """Return the single hidden Tk root, creating it on first call."""
    global _root
    with _lock:
        if _root is None:
            enable_dpi_awareness()
            _root = tk.Tk()
            _root.withdraw()
            apply_theme(_root)
        return _root
