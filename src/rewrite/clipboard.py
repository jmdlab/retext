"""Clipboard utilities — save, capture selection, replace, and restore.

Uses a two-pronged approach for keystroke simulation:
1. WM_COPY / WM_PASTE messages sent directly to the focused window
2. SendInput as fallback (for apps that don't handle WM_COPY)

This ensures compatibility with modern Win11 Notepad and other apps.
"""

from __future__ import annotations

import ctypes
import ctypes.wintypes
import time

import pyperclip

CLIPBOARD_DELAY: float = 0.25  # seconds after copy/paste before reading clipboard

# ---------------------------------------------------------------------------
# Win32 constants and API
# ---------------------------------------------------------------------------

WM_COPY = 0x0301
WM_PASTE = 0x0302

INPUT_KEYBOARD = 1
KEYEVENTF_KEYUP = 0x0002

VK_CONTROL = 0x11
VK_C = 0x43
VK_V = 0x56

_VK_MODIFIERS = (
    0x10,  # VK_SHIFT
    0x11,  # VK_CONTROL
    0x12,  # VK_MENU (Alt)
    0x5B,  # VK_LWIN
    0x5C,  # VK_RWIN
)

_user32 = ctypes.windll.user32
_GetForegroundWindow = _user32.GetForegroundWindow
_GetForegroundWindow.restype = ctypes.wintypes.HWND
_SendMessageW = _user32.SendMessageW
_SendMessageW.argtypes = [
    ctypes.wintypes.HWND, ctypes.wintypes.UINT,
    ctypes.wintypes.WPARAM, ctypes.wintypes.LPARAM,
]
_GetFocus = _user32.GetFocus
_AttachThreadInput = _user32.AttachThreadInput
_GetWindowThreadProcessId = _user32.GetWindowThreadProcessId
_GetCurrentThreadId = ctypes.windll.kernel32.GetCurrentThreadId
_SendInput = _user32.SendInput
_GetAsyncKeyState = _user32.GetAsyncKeyState


# ---------------------------------------------------------------------------
# Win32 SendInput structures (fallback)
# ---------------------------------------------------------------------------

class _KEYBDINPUT(ctypes.Structure):
    _fields_ = [
        ("wVk", ctypes.wintypes.WORD),
        ("wScan", ctypes.wintypes.WORD),
        ("dwFlags", ctypes.wintypes.DWORD),
        ("time", ctypes.wintypes.DWORD),
        ("dwExtraInfo", ctypes.POINTER(ctypes.c_ulong)),
    ]


class _INPUT(ctypes.Structure):
    class _U(ctypes.Union):
        _fields_ = [("ki", _KEYBDINPUT)]

    _anonymous_ = ("u",)
    _fields_ = [
        ("type", ctypes.wintypes.DWORD),
        ("u", _U),
    ]


def _make_key_input(vk: int, flags: int = 0) -> _INPUT:
    inp = _INPUT()
    inp.type = INPUT_KEYBOARD
    inp.ki.wVk = vk
    inp.ki.dwFlags = flags
    return inp


# ---------------------------------------------------------------------------
# Focus helpers
# ---------------------------------------------------------------------------

def _get_focused_hwnd() -> int:
    """Get the HWND of the control that has keyboard focus in the foreground window."""
    fg = _GetForegroundWindow()
    if not fg:
        return 0

    # Attach to the foreground thread to query its focus
    fg_thread = _GetWindowThreadProcessId(fg, None)
    our_thread = _GetCurrentThreadId()
    attached = False

    if fg_thread != our_thread:
        attached = _AttachThreadInput(our_thread, fg_thread, True)

    focused = _GetFocus()

    if attached:
        _AttachThreadInput(our_thread, fg_thread, False)

    return focused or fg


# ---------------------------------------------------------------------------
# Copy / Paste implementations
# ---------------------------------------------------------------------------

def _wm_copy() -> None:
    """Send WM_COPY to the focused control."""
    hwnd = _get_focused_hwnd()
    if hwnd:
        _SendMessageW(hwnd, WM_COPY, 0, 0)


def _wm_paste() -> None:
    """Send WM_PASTE to the focused control."""
    hwnd = _get_focused_hwnd()
    if hwnd:
        _SendMessageW(hwnd, WM_PASTE, 0, 0)


def _sendinput_combo(modifier_vk: int, key_vk: int) -> None:
    """Send a modifier+key combo via SendInput."""
    inputs = (_INPUT * 4)(
        _make_key_input(modifier_vk),
        _make_key_input(key_vk),
        _make_key_input(key_vk, KEYEVENTF_KEYUP),
        _make_key_input(modifier_vk, KEYEVENTF_KEYUP),
    )
    _SendInput(4, inputs, ctypes.sizeof(_INPUT))


def _release_all_modifiers() -> None:
    """Send key-up events for all modifiers to clear any stuck state."""
    release_vks = [0xA0, 0xA1, 0xA2, 0xA3, 0xA4, 0xA5, 0x5B, 0x5C]
    inputs = (_INPUT * len(release_vks))(
        *[_make_key_input(vk, KEYEVENTF_KEYUP) for vk in release_vks]
    )
    _SendInput(len(release_vks), inputs, ctypes.sizeof(_INPUT))


def _wait_for_modifiers_released(timeout: float = 1.5) -> None:
    """Block until the user physically releases all modifier keys."""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if not any(_GetAsyncKeyState(vk) & 0x8000 for vk in _VK_MODIFIERS):
            return
        time.sleep(0.02)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def save_clipboard() -> str | None:
    """Save current clipboard text content. Returns None if empty or non-text."""
    try:
        return pyperclip.paste()
    except Exception:
        return None


def capture_selection() -> str | None:
    """Copy the currently selected text via WM_COPY, then SendInput fallback."""
    from rewrite.logviewer import log_buffer

    original = save_clipboard()

    _release_all_modifiers()
    _wait_for_modifiers_released()
    time.sleep(0.05)

    strategies = [
        ("WM_COPY", _wm_copy),
        ("SendInput Ctrl+C", lambda: _sendinput_combo(VK_CONTROL, VK_C)),
    ]

    for name, copy_fn in strategies:
        pyperclip.copy("")
        time.sleep(0.05)

        copy_fn()
        time.sleep(CLIPBOARD_DELAY)

        captured = pyperclip.paste()
        if captured:
            log_buffer.append(f"{name} succeeded")
            return captured

        log_buffer.append(f"{name} got nothing")

    # Nothing was selected — restore original clipboard
    if original:
        pyperclip.copy(original)
    return None


def replace_selection(text: str) -> None:
    """Replace the current selection by pasting *text*."""
    pyperclip.copy(text)
    time.sleep(0.05)
    _wm_paste()
    time.sleep(CLIPBOARD_DELAY)


def restore_clipboard(original: str | None) -> None:
    """Restore the clipboard to its previous content after a short delay."""
    time.sleep(0.3)
    if original is not None:
        pyperclip.copy(original)
    else:
        pyperclip.copy("")
