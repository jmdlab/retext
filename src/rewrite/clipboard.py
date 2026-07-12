"""Clipboard utilities — save, capture selection, replace, and restore.

Uses SendInput exclusively for keystroke simulation, following the same
approach as AutoHotkey, Espanso, and PowerToys. The modifier-save/restore
pattern from PowerToys ensures clean Ctrl+C/V injection.
"""

from __future__ import annotations

import time

import pyperclip

from rewrite.win32input import (
    VK_C,
    VK_CONTROL,
    VK_MODIFIER_NAMES,
    VK_V,
    GetAsyncKeyState,
    get_clipboard_sequence,
    get_foreground_window,
    sendinput_combo,
)

# Max wait for the target app to answer Ctrl+C. Modern apps populate the
# clipboard in <16ms; the sequence-number poll below exits as soon as it lands.
CLIPBOARD_TIMEOUT: float = 0.5
_POLL_INTERVAL: float = 0.005

# Grace period after Ctrl+V so the target app reads the clipboard before
# restore_clipboard() overwrites it.
PASTE_SETTLE: float = 0.10


def _wait_for_clipboard_change(
    seq_before: int, timeout: float = CLIPBOARD_TIMEOUT,
) -> bool:
    """Poll the clipboard sequence number until it changes or timeout."""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if get_clipboard_sequence() != seq_before:
            return True
        time.sleep(_POLL_INTERVAL)
    return get_clipboard_sequence() != seq_before


# ---------------------------------------------------------------------------
# Modifier helpers
# ---------------------------------------------------------------------------

def _held_modifier_names() -> list[str]:
    return [
        name for vk, name in VK_MODIFIER_NAMES.items()
        if GetAsyncKeyState(vk) & 0x8000
    ]


def _wait_for_modifiers_released(timeout: float = 2.0) -> None:
    """Block until the user physically releases all modifier keys."""
    from rewrite.logviewer import log_buffer

    held = _held_modifier_names()
    if held:
        log_buffer.append(f"Waiting for release: {', '.join(held)}")

    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if not _held_modifier_names():
            time.sleep(0.05)
            # Double-check — debounce physical key bounce
            if not _held_modifier_names():
                log_buffer.append("All modifiers released")
                return
        time.sleep(0.02)

    still = _held_modifier_names()
    if still:
        log_buffer.append(f"Timeout — still held: {', '.join(still)}")


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def save_clipboard() -> str | None:
    """Return current clipboard text, or None."""
    try:
        return pyperclip.paste()
    except Exception:
        return None


def capture_selection() -> str | None:
    """Copy the currently selected text via SendInput Ctrl+C."""
    from rewrite.logviewer import log_buffer

    original = save_clipboard()

    _wait_for_modifiers_released()
    time.sleep(0.05)

    fg = get_foreground_window()
    log_buffer.append(f"Target: fg=0x{fg:X}")

    # Clear clipboard (synchronous), send Ctrl+C, poll for the change
    pyperclip.copy("")
    seq_before = get_clipboard_sequence()

    sent = sendinput_combo(VK_CONTROL, VK_C)
    if sent == 0:
        log_buffer.append("SendInput failed (UIPI? elevated target?)")

    changed = _wait_for_clipboard_change(seq_before)

    captured = pyperclip.paste()
    if changed and not captured:
        # Sequence bumped but text not readable yet (delayed rendering)
        time.sleep(0.02)
        captured = pyperclip.paste()
    if captured:
        log_buffer.append("Ctrl+C succeeded")
        return captured

    log_buffer.append("Ctrl+C got nothing")

    # Restore original clipboard on failure
    if original:
        pyperclip.copy(original)
    return None


def replace_selection(text: str) -> None:
    """Paste *text* over the current selection via SendInput Ctrl+V."""
    from rewrite.logviewer import log_buffer

    pyperclip.copy(text)  # synchronous — clipboard is set on return

    sent = sendinput_combo(VK_CONTROL, VK_V)
    if sent == 0:
        log_buffer.append("Paste SendInput failed")
    else:
        log_buffer.append("Pasted via SendInput Ctrl+V")

    time.sleep(PASTE_SETTLE)


def restore_clipboard(original: str | None) -> None:
    """Restore the clipboard to its previous content after a short delay."""
    time.sleep(0.3)
    pyperclip.copy(original if original is not None else "")
