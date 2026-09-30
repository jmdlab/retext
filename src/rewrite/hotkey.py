"""Global hotkey listener using pynput — register/unregister at runtime."""

from __future__ import annotations

import logging
import sys
import threading
import time
from collections.abc import Callable

from pynput import keyboard

IS_MAC = sys.platform == "darwin"

if IS_MAC:
    from rewrite.macinput import NAMED_VKS, VK_NAMES, vk_for_char
else:
    from rewrite.win32input import vk_for_char

log = logging.getLogger(__name__)

# Map string modifier names to sets of pynput Key variants they can appear as.
_MOD_VARIANTS: dict[str, set[keyboard.Key]] = {
    "ctrl": {keyboard.Key.ctrl_l, keyboard.Key.ctrl_r, keyboard.Key.ctrl},
    "shift": {keyboard.Key.shift_l, keyboard.Key.shift_r, keyboard.Key.shift},
    "alt": {keyboard.Key.alt_l, keyboard.Key.alt_r, keyboard.Key.alt},
    "win": {keyboard.Key.cmd, keyboard.Key.cmd_l, keyboard.Key.cmd_r},
}

# Reverse lookup: any pynput Key → canonical modifier name.
_KEY_TO_MOD: dict[keyboard.Key, str] = {}
for _name, _variants in _MOD_VARIANTS.items():
    for _v in _variants:
        _KEY_TO_MOD[_v] = _name

# Named keys (pynput Key.name spelling) → Windows virtual-key code.
_WIN_NAMED_VKS: dict[str, int] = {
    **{f"f{i}": 0x6F + i for i in range(1, 25)},  # F1=0x70 … F24=0x87
    "space": 0x20,
    "tab": 0x09,
    "enter": 0x0D,
    "backspace": 0x08,
    "delete": 0x2E,
    "insert": 0x2D,
    "home": 0x24,
    "end": 0x23,
    "page_up": 0x21,
    "page_down": 0x22,
    "up": 0x26,
    "down": 0x28,
    "left": 0x25,
    "right": 0x27,
    "esc": 0x1B,
    "escape": 0x1B,
    "pause": 0x13,
    "menu": 0x5D,
}

_NAMED_VKS: dict[str, int] = NAMED_VKS if IS_MAC else _WIN_NAMED_VKS

# Mac-friendly spellings accepted in hotkey strings.
_MOD_ALIASES: dict[str, str] = {
    "cmd": "win",
    "command": "win",
    "option": "alt",
    "opt": "alt",
    "control": "ctrl",
}


def _vk_for_key(part: str) -> int | None:
    """Return the Windows VK code for a hotkey part, or None if unsupported."""
    if part in _NAMED_VKS:
        return _NAMED_VKS[part]
    if len(part) != 1:
        return None
    if not IS_MAC and ("a" <= part <= "z" or "0" <= part <= "9"):
        return ord(part.upper())
    # Punctuation etc. — resolve against the current keyboard layout
    return vk_for_char(part)


def _parse_hotkey(
    hotkey_str: str,
) -> tuple[frozenset[str], int]:
    """Parse 'ctrl+shift+r' into canonical modifier names and a VK code."""
    parts = [p.strip().lower() for p in hotkey_str.split("+")]
    modifiers: set[str] = set()
    vk: int | None = None

    for part in parts:
        part = _MOD_ALIASES.get(part, part)
        if part in _MOD_VARIANTS:
            modifiers.add(part)
            continue
        vk = _vk_for_key(part)
        if vk is None:
            msg = f"Unsupported key in hotkey '{hotkey_str}': {part!r}"
            raise ValueError(msg)

    if vk is None:
        msg = f"No trigger key found in hotkey: {hotkey_str}"
        raise ValueError(msg)

    return frozenset(modifiers), vk


# Display order and symbols for macOS menus (⌃⌥⇧⌘, Apple HIG order).
_MAC_MOD_SYMBOLS: dict[str, str] = {
    "ctrl": "\u2303", "alt": "\u2325", "shift": "\u21e7", "win": "\u2318",
}
_MAC_KEY_SYMBOLS: dict[str, str] = {
    "space": "Space", "tab": "\u21e5", "enter": "\u21a9",
    "backspace": "\u232b", "delete": "\u2326", "esc": "\u238b",
    "escape": "\u238b", "up": "\u2191", "down": "\u2193",
    "left": "\u2190", "right": "\u2192", "home": "\u2196", "end": "\u2198",
    "page_up": "\u21de", "page_down": "\u21df",
}


def format_hotkey_mac(hotkey_str: str) -> str:
    """Render 'ctrl+alt+r' as '⌃⌥R' for macOS menus."""
    parts = [p.strip().lower() for p in hotkey_str.split("+")]
    mods = {_MOD_ALIASES.get(p, p) for p in parts} & _MAC_MOD_SYMBOLS.keys()
    keys = [
        p for p in parts if _MOD_ALIASES.get(p, p) not in _MAC_MOD_SYMBOLS
    ]
    symbols = "".join(s for m, s in _MAC_MOD_SYMBOLS.items() if m in mods)
    key = keys[-1] if keys else ""
    return symbols + _MAC_KEY_SYMBOLS.get(key, key.upper())


def hotkey_string(mods: set[str], key_name: str) -> str:
    """Build a canonical hotkey string ('ctrl+alt+r') from recorded parts.

    On macOS the Command modifier is written as 'cmd' for readability.
    """
    order = ["ctrl", "alt", "shift", "win"]
    names = [
        "cmd" if IS_MAC and m == "win" else m
        for m in order if m in mods
    ]
    return "+".join([*names, key_name])


def _pass_through(_event_type: int, event: object) -> object:
    return event


def listener_options() -> dict:
    """Platform-specific pynput Listener options.

    macOS: an intercepting (active) event tap needs only the Accessibility
    permission, while pynput's default listen-only tap also needs Input
    Monitoring. Events are passed through untouched.
    """
    return {"darwin_intercept": _pass_through} if IS_MAC else {}


def key_name_for_vk(vk: int) -> str | None:
    """macOS: return the hotkey name for a recorded key code, or None."""
    return VK_NAMES.get(vk) if IS_MAC else None


class HotkeyManager:
    """Manages a single global hotkey that can be swapped at runtime."""

    _DEBOUNCE_SECS = 0.5

    def __init__(self) -> None:
        self._current_hotkey: str | None = None
        self._callback: Callable[[], None] | None = None
        self._listener: keyboard.Listener | None = None
        self._modifiers: frozenset[str] = frozenset()
        self._trigger_vk: int | None = None
        self._active_mods: set[str] = set()
        self._last_fire: float = 0.0

    def _on_press(
        self, key: keyboard.Key | keyboard.KeyCode | None,
    ) -> None:
        """Track pressed keys and fire callback on hotkey match."""
        if key is None:
            return

        # Track modifier state
        if isinstance(key, keyboard.Key):
            mod = _KEY_TO_MOD.get(key)
            if mod:
                self._active_mods.add(mod)
                return
            # Special non-modifier key (F9, Home…) — may be the trigger
            vk = getattr(key.value, "vk", None)
        else:
            vk = getattr(key, "vk", None)

        if self._trigger_vk is None or self._callback is None:
            return

        now = time.monotonic()
        if (
            vk == self._trigger_vk
            and self._modifiers <= self._active_mods
            and now - self._last_fire > self._DEBOUNCE_SECS
        ):
            self._last_fire = now
            log.info("Hotkey triggered: %s", self._current_hotkey)
            threading.Thread(target=self._callback, daemon=True).start()

    def _on_release(
        self, key: keyboard.Key | keyboard.KeyCode | None,
    ) -> None:
        """Track released modifiers."""
        if isinstance(key, keyboard.Key):
            mod = _KEY_TO_MOD.get(key)
            if mod:
                self._active_mods.discard(mod)

    def register(self, hotkey: str, callback: Callable[[], None]) -> None:
        """Register a global hotkey. Unregisters the previous one first."""
        self.unregister()
        self._modifiers, self._trigger_vk = _parse_hotkey(hotkey)
        self._current_hotkey = hotkey
        self._callback = callback
        self._listener = keyboard.Listener(
            on_press=self._on_press,
            on_release=self._on_release,
            **listener_options(),
        )
        self._listener.daemon = True
        self._listener.start()
        log.info("Hotkey registered: %s", hotkey)

    def unregister(self) -> None:
        """Unregister the current hotkey, if any."""
        if self._listener is not None:
            self._listener.stop()
            self._listener = None
        self._current_hotkey = None
        self._callback = None
        self._trigger_vk = None
        self._modifiers = frozenset()
        self._active_mods.clear()

    @property
    def is_listening(self) -> bool:
        """False if the listener died — e.g. its event tap was refused."""
        return self._listener is not None and self._listener.is_alive()

    @property
    def current_hotkey(self) -> str | None:
        """The currently registered hotkey string, or None."""
        return self._current_hotkey
