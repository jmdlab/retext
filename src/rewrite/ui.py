"""Shared Tk look: DPI awareness, Windows 11 palette, fonts, ttk styles."""

from __future__ import annotations

import contextlib
import ctypes
import tkinter as tk
from tkinter import ttk

# Windows 11 "Settings" light palette.
PAGE_BG = "#f3f3f3"
CARD_BG = "#fbfbfb"
CARD_BORDER = "#e5e5e5"
TEXT = "#1a1a1a"
TEXT_SECONDARY = "#5d5d5d"
TEXT_DISABLED = "#a0a0a0"

BODY = ("Segoe UI Variable Text", 10)
BODY_STRONG = ("Segoe UI Variable Text Semibold", 10)
CAPTION = ("Segoe UI Variable Small", 9)
TITLE = ("Segoe UI Variable Display Semibold", 20)
MONO = ("Cascadia Mono", 10)

_DPI_AWARE_PER_MONITOR_V2 = -4


def enable_dpi_awareness() -> None:
    """Render natively at the monitor's DPI instead of being bitmap-scaled.

    Must run before the first Tk() is created, or Windows blurs every window.
    """
    with contextlib.suppress(AttributeError, OSError):
        ctypes.windll.user32.SetProcessDpiAwarenessContext(
            ctypes.c_void_p(_DPI_AWARE_PER_MONITOR_V2),
        )
        return
    with contextlib.suppress(AttributeError, OSError):
        ctypes.windll.shcore.SetProcessDpiAwareness(2)


def px(widget: tk.Misc, value: float) -> int:
    """Convert a 96-DPI design pixel value into real pixels for ``widget``."""
    return round(value * widget.winfo_fpixels("1i") / 96)


def apply_theme(root: tk.Misc) -> None:
    """Configure the ttk styles used by every Retext window."""
    style = ttk.Style(root)
    with contextlib.suppress(tk.TclError):
        style.theme_use("vista")

    # Only the combobox dropdown needs the option DB; a global "*Font" would
    # set -font on every ttk widget and override the styles below.
    root.option_add("*TCombobox*Listbox.font", BODY)

    style.configure(".", font=BODY, foreground=TEXT)
    style.configure("Page.TFrame", background=PAGE_BG)
    style.configure("Card.TFrame", background=CARD_BG)
    style.configure("Title.TLabel", background=PAGE_BG, font=TITLE)
    style.configure(
        "Section.TLabel", background=PAGE_BG, font=BODY_STRONG,
    )
    style.configure("Card.TLabel", background=CARD_BG)
    style.configure(
        "CardHint.TLabel", background=CARD_BG,
        foreground=TEXT_SECONDARY, font=CAPTION,
    )
    style.configure(
        "Keycap.TLabel", background=CARD_BG, font=BODY_STRONG,
    )
    for kind in ("TCheckbutton", "TRadiobutton"):
        style.configure(f"Card.{kind}", background=CARD_BG)
        style.map(
            f"Card.{kind}", foreground=[("disabled", TEXT_DISABLED)],
        )
    # Inputs and buttons share one height (32 px at 100 %).
    style.configure("TButton", padding=(px(root, 12), px(root, 4)))
    style.configure("TEntry", padding=(px(root, 6), px(root, 5)))
    style.configure("TCombobox", padding=(px(root, 6), px(root, 5)))
