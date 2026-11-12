"""Tkinter settings window — Gemini API key, model, hotkey."""

from __future__ import annotations

import contextlib
import tkinter as tk
from pathlib import Path
from tkinter import ttk
from typing import TYPE_CHECKING

from pynput import keyboard as pynput_kb

from rewrite import startup, ui
from rewrite.config import DEFAULT_CONFIG, load_config, save_config
from rewrite.providers import ollama

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

        from rewrite.tkroot import get_root

        get_root()  # ensure hidden root exists
        self.root = tk.Toplevel()
        self.root.title("Retext \u2014 Settings")
        self.root.configure(background=ui.PAGE_BG)
        self.root.resizable(False, False)  # size follows content

        if icon_path and icon_path.exists():
            with contextlib.suppress(tk.TclError):
                self.root.iconbitmap(str(icon_path))

        self._build_ui()
        self._load_values()

    # ------------------------------------------------------------------
    # UI
    # ------------------------------------------------------------------

    def _build_ui(self) -> None:
        r = self.root
        page = ttk.Frame(r, style="Page.TFrame", padding=ui.px(r, 24))
        page.pack(fill="both", expand=True)

        ttk.Label(page, text="Settings", style="Title.TLabel").pack(
            anchor="w", pady=(0, ui.px(r, 16)),
        )

        # --- Correction engine ---
        engine_card = self._section(page, "Correction engine")
        choice = self._row(
            engine_card, "Engine", "Where your text gets corrected",
        )
        self.provider_var = tk.StringVar()
        for value, label in (("gemini", "Gemini"), ("ollama", "Ollama (local)")):
            ttk.Radiobutton(
                choice, text=label, value=value, style="Card.TRadiobutton",
                variable=self.provider_var, command=self._sync_provider_state,
            ).pack(side="left", padx=(ui.px(r, 12), 0))

        # Gemini rows (shown when Gemini is selected)
        self.gemini_frame = tk.Frame(engine_card, background=ui.CARD_BG)
        self._divider(self.gemini_frame)
        key_ctl = self._row(
            self.gemini_frame, "API key",
            "Stored in Windows Credential Manager",
        )
        self.gemini_key_var = tk.StringVar()
        self.gemini_key_entry = ttk.Entry(
            key_ctl, textvariable=self.gemini_key_var, width=26, show="•",
        )
        self.gemini_key_entry.pack(side="left")
        self.gem_show_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(
            key_ctl, text="Show", style="Card.TCheckbutton",
            variable=self.gem_show_var, command=self._toggle_key,
        ).pack(side="left", padx=(ui.px(r, 8), 0))

        self._divider(self.gemini_frame)
        model_ctl = self._row(self.gemini_frame, "Model", "Any Gemini model name")
        self.gemini_model_var = tk.StringVar()
        ttk.Entry(
            model_ctl, textvariable=self.gemini_model_var, width=26,
        ).pack(side="left")

        # Ollama rows (shown when Ollama is selected)
        self.ollama_frame = tk.Frame(engine_card, background=ui.CARD_BG)
        self._divider(self.ollama_frame)
        self.ollama_status_var = tk.StringVar()
        oll_ctl = self._row(self.ollama_frame, "Model", self.ollama_status_var)
        self.ollama_model_var = tk.StringVar()
        self.ollama_model_box = ttk.Combobox(
            oll_ctl, textvariable=self.ollama_model_var, width=22,
        )
        self.ollama_model_box.pack(side="left")
        ttk.Button(
            oll_ctl, text="Refresh", command=self._refresh_ollama_models,
        ).pack(side="left", padx=(ui.px(r, 8), 0))

        self._divider(self.ollama_frame)
        upd_ctl = self._row(
            self.ollama_frame, "Keep model updated",
            "Checks for a newer version daily",
        )
        self.ollama_auto_update_var = tk.BooleanVar(value=True)
        ttk.Checkbutton(
            upd_ctl, style="Card.TCheckbutton",
            variable=self.ollama_auto_update_var,
        ).pack(side="left")

        # --- Shortcut ---
        hotkey_card = self._section(page, "Shortcut")
        hk_ctl = self._row(
            hotkey_card, "Correct selection",
            "Select text anywhere, then press it",
        )
        self.hotkey_var = tk.StringVar()
        self.hotkey_label_var = tk.StringVar()
        self.hotkey_var.trace_add("write", self._on_hotkey_var_changed)
        ttk.Label(
            hk_ctl, textvariable=self.hotkey_label_var, style="Keycap.TLabel",
        ).pack(side="left", padx=(0, ui.px(r, 12)))
        self.record_btn = ttk.Button(
            hk_ctl, text="Change", command=self._start_recording,
        )
        self.record_btn.pack(side="left")
        ttk.Button(
            hk_ctl, text="Reset", command=self._reset_hotkey,
        ).pack(side="left", padx=(ui.px(r, 8), 0))

        # --- General ---
        general_card = self._section(page, "General")
        start_ctl = self._row(
            general_card, "Launch at Windows startup",
            "Retext waits in the system tray",
        )
        self.startup_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(
            start_ctl, style="Card.TCheckbutton", variable=self.startup_var,
        ).pack(side="left")

        # --- Footer ---
        footer = ttk.Frame(page, style="Page.TFrame")
        footer.pack(fill="x", pady=(ui.px(r, 8), 0))
        ttk.Button(footer, text="Cancel", command=r.destroy).pack(side="right")
        ttk.Button(
            footer, text="Save", default="active", command=self._on_save_click,
        ).pack(side="right", padx=(0, ui.px(r, 8)))
        r.bind("<Return>", lambda _e: self._on_save_click())
        r.bind("<Escape>", lambda _e: r.destroy())

    # --- layout helpers -------------------------------------------------

    def _section(self, parent: tk.Misc, title: str) -> tk.Frame:
        """A section heading followed by a bordered card; returns the card."""
        ttk.Label(parent, text=title, style="Section.TLabel").pack(
            anchor="w", pady=(0, ui.px(self.root, 6)),
        )
        card = tk.Frame(
            parent, background=ui.CARD_BG,
            highlightthickness=1, highlightbackground=ui.CARD_BORDER,
        )
        card.pack(fill="x", pady=(0, ui.px(self.root, 20)))
        return card

    def _row(
        self, card: tk.Misc, title: str, hint: str | tk.StringVar,
    ) -> ttk.Frame:
        """A settings row: title + hint on the left, controls on the right."""
        r = self.root
        row = ttk.Frame(card, style="Card.TFrame", padding=(ui.px(r, 16), ui.px(r, 12)))
        row.pack(fill="x")
        row.columnconfigure(0, weight=1)

        text = ttk.Frame(row, style="Card.TFrame")
        text.grid(row=0, column=0, sticky="w", padx=(0, ui.px(r, 24)))
        ttk.Label(text, text=title, style="Card.TLabel").pack(anchor="w")
        hint_opts: dict = {"style": "CardHint.TLabel", "wraplength": ui.px(r, 280)}
        if isinstance(hint, tk.StringVar):
            hint_opts["textvariable"] = hint
        else:
            hint_opts["text"] = hint
        ttk.Label(text, **hint_opts).pack(anchor="w")

        controls = ttk.Frame(row, style="Card.TFrame")
        controls.grid(row=0, column=1, sticky="e")
        return controls

    def _divider(self, parent: tk.Misc) -> None:
        tk.Frame(parent, height=1, background=ui.CARD_BORDER).pack(fill="x")

    def _on_hotkey_var_changed(self, *_args: object) -> None:
        self.hotkey_label_var.set(format_hotkey(self.hotkey_var.get()))

    def _toggle_key(self) -> None:
        show = "" if self.gem_show_var.get() else "•"
        self.gemini_key_entry.config(show=show)

    def _refresh_ollama_models(self) -> None:
        """Fill the model dropdown with installed models (local call, fast)."""
        default = DEFAULT_CONFIG["ollama_model"]
        try:
            installed = ollama.list_models(self._ollama_url())
        except ollama.OllamaError:
            self.ollama_model_box["values"] = [default]
            self.ollama_status_var.set(
                "Ollama isn't running yet — Retext starts it on Save",
            )
            return
        values = installed if default in installed else [default, *installed]
        self.ollama_model_box["values"] = values
        self.ollama_status_var.set(
            f"{len(installed)} installed · others download on Save",
        )

    def _ollama_url(self) -> str:
        return self.config.get("ollama_url", DEFAULT_CONFIG["ollama_url"])

    def _sync_provider_state(self) -> None:
        """Show only the settings of the selected engine."""
        use_ollama = self.provider_var.get() == "ollama"
        shown, hidden = (
            (self.ollama_frame, self.gemini_frame) if use_ollama
            else (self.gemini_frame, self.ollama_frame)
        )
        hidden.pack_forget()
        shown.pack(fill="x")
        if use_ollama:
            self._refresh_ollama_models()

    def _load_values(self) -> None:
        cfg = self.config
        self.provider_var.set(cfg.get("provider", "gemini"))
        self.ollama_model_var.set(
            cfg.get("ollama_model", DEFAULT_CONFIG["ollama_model"]),
        )
        self.ollama_auto_update_var.set(cfg.get("ollama_auto_update", True))
        self._sync_provider_state()
        self.gemini_key_var.set(cfg.get("gemini_api_key", ""))
        self.gemini_model_var.set(
            cfg.get("gemini_model", "gemini-2.5-flash"),
        )
        self.hotkey_var.set(cfg.get("hotkey", "ctrl+shift+r"))
        self.startup_var.set(startup.is_enabled())

    # ------------------------------------------------------------------
    # Hotkey recording
    # ------------------------------------------------------------------

    def _reset_hotkey(self) -> None:
        """Reset hotkey to default."""
        self.hotkey_var.set(DEFAULT_CONFIG["hotkey"])

    def _start_recording(self) -> None:
        if hasattr(self, "_rec_listener") and self._rec_listener is not None:
            self._rec_listener.stop()
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
            pynput_kb.Key.cmd_l: "win",
            pynput_kb.Key.cmd_r: "win",
        }
        if key in mod_map:
            self._rec_modifiers.add(mod_map[key])
            return

        if isinstance(key, pynput_kb.KeyCode):
            vk = key.vk
            # With Ctrl held, key.char is a control character — derive the
            # name from the VK code for letters and digits instead.
            if vk is not None and (0x30 <= vk <= 0x39 or 0x41 <= vk <= 0x5A):
                key_name = chr(vk).lower()
            elif key.char and key.char.isprintable():
                key_name = key.char.lower()
            else:
                return
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
        self.record_btn.config(text="Change")

    # ------------------------------------------------------------------
    # Save
    # ------------------------------------------------------------------

    def _on_save_click(self) -> None:
        self.config["provider"] = self.provider_var.get()
        self.config["ollama_model"] = (
            self.ollama_model_var.get().strip()
            or DEFAULT_CONFIG["ollama_model"]
        )
        self.config["ollama_auto_update"] = self.ollama_auto_update_var.get()
        self.config["gemini_api_key"] = self.gemini_key_var.get()
        self.config["gemini_model"] = self.gemini_model_var.get()
        self.config["hotkey"] = self.hotkey_var.get()

        save_config(self.config)
        startup.set_enabled(self.startup_var.get())
        if self.on_save:
            self.on_save(self.config)
        self.root.destroy()

    def show(self) -> None:
        self.root.lift()
        self.root.focus_force()
        self.root.mainloop()


_KEY_LABELS = {"ctrl": "Ctrl", "alt": "Alt", "shift": "Shift", "win": "Win"}


def format_hotkey(hotkey: str) -> str:
    """Turn a stored hotkey like ``ctrl+alt+r`` into ``Ctrl + Alt + R``."""
    if hotkey in ("", "…"):  # empty, or recording in progress
        return hotkey
    parts = []
    for part in hotkey.split("+"):
        label = _KEY_LABELS.get(part)
        if label is None:
            label = part.upper() if len(part) == 1 else part.replace("_", " ").title()
        parts.append(label)
    return " + ".join(parts)


def open_settings(
    on_save: Callable[[dict], None] | None = None,
    icon_path: Path | None = None,
) -> None:
    """Open the settings window."""
    window = SettingsWindow(on_save=on_save, icon_path=icon_path)
    window.show()
