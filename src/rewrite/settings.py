"""Tkinter settings window — Gemini API key, model, hotkey."""

from __future__ import annotations

import contextlib
import tkinter as tk
from pathlib import Path
from tkinter import ttk
from typing import TYPE_CHECKING

from pynput import keyboard as pynput_kb

from rewrite.config import load_config, save_config

if TYPE_CHECKING:
    from collections.abc import Callable


class SettingsWindow:
    """Modal settings window for Retext."""

    def __init__(
        self,
        on_save: Callable[[dict], None] | None = None,
        icon_path: Path | None = None,
    ) -> None:
        self.on_save = on_save
        self.config = load_config()

        self.root = (
            tk.Toplevel() if tk._default_root else tk.Tk()
        )
        self.root.title("Retext \u2014 Settings")
        self.root.geometry("400x300")
        self.root.resizable(False, False)

        if icon_path and icon_path.exists():
            with contextlib.suppress(tk.TclError):
                self.root.iconbitmap(str(icon_path))

        self._build_ui()
        self._load_values()

    # ------------------------------------------------------------------
    # UI
    # ------------------------------------------------------------------

    def _build_ui(self) -> None:
        main = ttk.Frame(self.root, padding=16)
        main.pack(fill="both", expand=True)

        # --- Gemini ---
        gem_frame = ttk.LabelFrame(main, text="Gemini", padding=12)
        gem_frame.pack(fill="x", pady=(0, 12))

        ttk.Label(gem_frame, text="API Key:").pack(anchor="w")
        self.gemini_key_var = tk.StringVar()
        key_row = ttk.Frame(gem_frame)
        key_row.pack(anchor="w", pady=2)
        self.gemini_key_entry = ttk.Entry(
            key_row,
            textvariable=self.gemini_key_var,
            width=36,
            show="\u2022",
        )
        self.gemini_key_entry.pack(side="left")
        self.gem_show_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(
            key_row,
            text="Show",
            variable=self.gem_show_var,
            command=self._toggle_key,
        ).pack(side="left", padx=4)

        ttk.Label(gem_frame, text="Model:").pack(anchor="w", pady=(8, 0))
        self.gemini_model_var = tk.StringVar()
        ttk.Entry(
            gem_frame, textvariable=self.gemini_model_var, width=30,
        ).pack(anchor="w", pady=2)

        # --- Hotkey ---
        hotkey_frame = ttk.LabelFrame(main, text="Hotkey", padding=12)
        hotkey_frame.pack(fill="x", pady=(0, 12))

        hotkey_row = ttk.Frame(hotkey_frame)
        hotkey_row.pack(fill="x")
        self.hotkey_var = tk.StringVar()
        self.hotkey_display = ttk.Entry(
            hotkey_row,
            textvariable=self.hotkey_var,
            width=20,
            state="readonly",
        )
        self.hotkey_display.pack(side="left")
        self.record_btn = ttk.Button(
            hotkey_row, text="Record", command=self._start_recording,
        )
        self.record_btn.pack(side="left", padx=8)
        ttk.Button(
            hotkey_row, text="Reset", command=self._reset_hotkey,
        ).pack(side="left")

        # --- Buttons ---
        btn_row = ttk.Frame(main)
        btn_row.pack(fill="x", pady=(8, 0))
        ttk.Button(
            btn_row, text="Cancel", command=self.root.destroy,
        ).pack(side="right")
        ttk.Button(
            btn_row, text="Save", command=self._on_save_click,
        ).pack(side="right", padx=(0, 8))

    def _toggle_key(self) -> None:
        show = "" if self.gem_show_var.get() else "\u2022"
        self.gemini_key_entry.config(show=show)

    def _load_values(self) -> None:
        cfg = self.config
        self.gemini_key_var.set(cfg.get("gemini_api_key", ""))
        self.gemini_model_var.set(
            cfg.get("gemini_model", "gemini-2.5-flash"),
        )
        self.hotkey_var.set(cfg.get("hotkey", "ctrl+shift+r"))

    # ------------------------------------------------------------------
    # Hotkey recording
    # ------------------------------------------------------------------

    def _reset_hotkey(self) -> None:
        """Reset hotkey to default (ctrl+shift+r)."""
        from rewrite.config import DEFAULT_CONFIG

        self.hotkey_var.set(DEFAULT_CONFIG["hotkey"])

    def _start_recording(self) -> None:
        self.record_btn.config(text="Press keys\u2026")
        self.hotkey_var.set("\u2026")
        self._rec_modifiers: set[str] = set()
        self._rec_listener = pynput_kb.Listener(
            on_press=self._on_key_during_recording,
        )
        self._rec_listener.daemon = True
        self._rec_listener.start()

    def _on_key_during_recording(
        self,
        key: pynput_kb.Key | pynput_kb.KeyCode | None,
    ) -> None:
        if key is None:
            return

        mod_map = {
            pynput_kb.Key.ctrl_l: "ctrl",
            pynput_kb.Key.ctrl_r: "ctrl",
            pynput_kb.Key.shift_l: "shift",
            pynput_kb.Key.shift_r: "shift",
            pynput_kb.Key.alt_l: "alt",
            pynput_kb.Key.alt_r: "alt",
            pynput_kb.Key.cmd: "win",
        }
        if key in mod_map:
            self._rec_modifiers.add(mod_map[key])
            return

        if isinstance(key, pynput_kb.KeyCode) and key.char:
            key_name = key.char.lower()
        elif isinstance(key, pynput_kb.Key):
            key_name = key.name
        else:
            return

        parts = [*sorted(self._rec_modifiers), key_name]
        hotkey_str = "+".join(parts)

        self._rec_listener.stop()
        self.root.after(0, self._finish_recording, hotkey_str)
        return False

    def _finish_recording(self, hotkey_str: str) -> None:
        self.hotkey_var.set(hotkey_str)
        self.record_btn.config(text="Record")

    # ------------------------------------------------------------------
    # Save
    # ------------------------------------------------------------------

    def _on_save_click(self) -> None:
        self.config["gemini_api_key"] = self.gemini_key_var.get()
        self.config["gemini_model"] = self.gemini_model_var.get()
        self.config["hotkey"] = self.hotkey_var.get()

        save_config(self.config)
        if self.on_save:
            self.on_save(self.config)
        self.root.destroy()

    def show(self) -> None:
        self.root.lift()
        self.root.focus_force()
        self.root.mainloop()


def open_settings(
    on_save: Callable[[dict], None] | None = None,
    icon_path: Path | None = None,
) -> None:
    """Open the settings window."""
    window = SettingsWindow(on_save=on_save, icon_path=icon_path)
    window.show()
