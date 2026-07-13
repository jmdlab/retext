"""Low-level Win32 SendInput bindings for keystroke simulation.

Uses SendInput exclusively — the same approach as AutoHotkey, Espanso,
and PowerToys. Correct 64-bit struct layout (INPUT = 40 bytes).
"""

from __future__ import annotations

import ctypes
import ctypes.wintypes

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

INPUT_KEYBOARD = 1
KEYEVENTF_KEYUP = 0x0002

VK_CONTROL = 0x11
VK_C = 0x43
VK_V = 0x56

# Physical modifier VKs for polling key state.
VK_MODIFIER_NAMES: dict[int, str] = {
    0x10: "Shift",
    0x11: "Ctrl",
    0x12: "Alt",
    0x5B: "LWin",
    0x5C: "RWin",
}

# ---------------------------------------------------------------------------
# Win32 API bindings
# ---------------------------------------------------------------------------

_user32 = ctypes.windll.user32
_kernel32 = ctypes.windll.kernel32

_GetForegroundWindow = _user32.GetForegroundWindow
_GetForegroundWindow.restype = ctypes.wintypes.HWND
_GetForegroundWindow.argtypes = []

GetAsyncKeyState = _user32.GetAsyncKeyState
GetAsyncKeyState.argtypes = [ctypes.c_int]
GetAsyncKeyState.restype = ctypes.wintypes.SHORT

_GetClipboardSequenceNumber = _user32.GetClipboardSequenceNumber
_GetClipboardSequenceNumber.argtypes = []
_GetClipboardSequenceNumber.restype = ctypes.wintypes.DWORD

_VkKeyScanW = _user32.VkKeyScanW
_VkKeyScanW.argtypes = [ctypes.wintypes.WCHAR]
_VkKeyScanW.restype = ctypes.wintypes.SHORT


# ---------------------------------------------------------------------------
# SendInput structures (correct 64-bit layout)
#
# The union must include MOUSEINPUT (the largest member) so that
# sizeof(INPUT) == 40 on 64-bit Windows. Without this, SendInput
# silently misreads array elements beyond the first.
# ---------------------------------------------------------------------------

class _MOUSEINPUT(ctypes.Structure):
    _fields_ = [
        ("dx", ctypes.c_long), ("dy", ctypes.c_long),
        ("mouseData", ctypes.wintypes.DWORD),
        ("dwFlags", ctypes.wintypes.DWORD),
        ("time", ctypes.wintypes.DWORD),
        ("dwExtraInfo", ctypes.c_uint64),
    ]


class _KEYBDINPUT(ctypes.Structure):
    _fields_ = [
        ("wVk", ctypes.wintypes.WORD), ("wScan", ctypes.wintypes.WORD),
        ("dwFlags", ctypes.wintypes.DWORD),
        ("time", ctypes.wintypes.DWORD),
        ("dwExtraInfo", ctypes.c_uint64),
    ]


class _HARDWAREINPUT(ctypes.Structure):
    _fields_ = [
        ("uMsg", ctypes.wintypes.DWORD),
        ("wParamL", ctypes.wintypes.WORD), ("wParamH", ctypes.wintypes.WORD),
    ]


class _INPUT_UNION(ctypes.Union):
    _fields_ = [  # noqa: RUF012 — ctypes reads _fields_ as a class attribute
        ("mi", _MOUSEINPUT), ("ki", _KEYBDINPUT), ("hi", _HARDWAREINPUT),
    ]


class _INPUT(ctypes.Structure):
    _fields_ = [("type", ctypes.wintypes.DWORD), ("union", _INPUT_UNION)]


_SendInput = _user32.SendInput
_SendInput.argtypes = [ctypes.wintypes.UINT, ctypes.POINTER(_INPUT), ctypes.c_int]
_SendInput.restype = ctypes.wintypes.UINT


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def get_foreground_window() -> int:
    """Return the HWND of the foreground window, or 0."""
    return _GetForegroundWindow() or 0


def get_clipboard_sequence() -> int:
    """Return the clipboard sequence number — bumps on every clipboard change."""
    return _GetClipboardSequenceNumber()


def vk_for_char(char: str) -> int | None:
    """Return the VK code for a character on the current keyboard layout."""
    result = _VkKeyScanW(char)
    if result == -1:
        return None
    return result & 0xFF


def sendinput_combo(modifier_vk: int, key_vk: int) -> int:
    """Send a modifier+key combo via SendInput. Returns number of events sent.

    All 4 events (modifier down, key down, key up, modifier up) are sent
    atomically — no other input can be interleaved.
    """
    inputs = (_INPUT * 4)()
    for i, (vk, flags) in enumerate([
        (modifier_vk, 0),
        (key_vk, 0),
        (key_vk, KEYEVENTF_KEYUP),
        (modifier_vk, KEYEVENTF_KEYUP),
    ]):
        inputs[i].type = INPUT_KEYBOARD
        inputs[i].union.ki.wVk = vk
        inputs[i].union.ki.dwFlags = flags
    return _SendInput(4, inputs, ctypes.sizeof(_INPUT))
