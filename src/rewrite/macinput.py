"""Low-level macOS keystroke simulation — Quartz CGEvent bindings.

Drop-in counterpart to win32input.py: exposes the same names so
clipboard.py and hotkey.py work unchanged. Key codes are macOS virtual
key codes (kVK_* from Carbon's Events.h), which map to physical key
positions on an ANSI keyboard.

Posting events requires the Accessibility permission; reading key state
and listening for the hotkey require Input Monitoring.
"""

from __future__ import annotations

import Quartz
from AppKit import NSPasteboard, NSWorkspace
from ApplicationServices import (
    AXIsProcessTrusted,
    AXIsProcessTrustedWithOptions,
    kAXTrustedCheckOptionPrompt,
)

# ---------------------------------------------------------------------------
# Key codes
# ---------------------------------------------------------------------------

# The shortcut modifier for copy/paste — ⌘ on macOS. Named VK_CONTROL so
# clipboard.py can send "modifier + C" identically on both platforms.
VK_CONTROL = 0x37
VK_C = 0x08
VK_V = 0x09

# Physical modifier key codes for polling key state.
VK_MODIFIER_NAMES: dict[int, str] = {
    0x37: "Cmd",
    0x36: "RCmd",
    0x38: "Shift",
    0x3C: "RShift",
    0x3A: "Option",
    0x3D: "ROption",
    0x3B: "Ctrl",
    0x3E: "RCtrl",
}

# Character → key code on the ANSI layout.
CHAR_VKS: dict[str, int] = {
    "a": 0x00, "s": 0x01, "d": 0x02, "f": 0x03, "h": 0x04, "g": 0x05,
    "z": 0x06, "x": 0x07, "c": 0x08, "v": 0x09, "b": 0x0B, "q": 0x0C,
    "w": 0x0D, "e": 0x0E, "r": 0x0F, "y": 0x10, "t": 0x11, "1": 0x12,
    "2": 0x13, "3": 0x14, "4": 0x15, "6": 0x16, "5": 0x17, "=": 0x18,
    "9": 0x19, "7": 0x1A, "-": 0x1B, "8": 0x1C, "0": 0x1D, "]": 0x1E,
    "o": 0x1F, "u": 0x20, "[": 0x21, "i": 0x22, "p": 0x23, "l": 0x25,
    "j": 0x26, "'": 0x27, "k": 0x28, ";": 0x29, "\\": 0x2A, ",": 0x2B,
    "/": 0x2C, "n": 0x2D, "m": 0x2E, ".": 0x2F, "`": 0x32,
}

# Named keys (pynput Key.name spelling) → key code.
NAMED_VKS: dict[str, int] = {
    "f1": 0x7A, "f2": 0x78, "f3": 0x63, "f4": 0x76, "f5": 0x60,
    "f6": 0x61, "f7": 0x62, "f8": 0x64, "f9": 0x65, "f10": 0x6D,
    "f11": 0x67, "f12": 0x6F, "f13": 0x69, "f14": 0x6B, "f15": 0x71,
    "f16": 0x6A, "f17": 0x40, "f18": 0x4F, "f19": 0x50, "f20": 0x5A,
    "space": 0x31,
    "tab": 0x30,
    "enter": 0x24,
    "backspace": 0x33,
    "delete": 0x75,
    "home": 0x73,
    "end": 0x77,
    "page_up": 0x74,
    "page_down": 0x79,
    "up": 0x7E,
    "down": 0x7D,
    "left": 0x7B,
    "right": 0x7C,
    "esc": 0x35,
    "escape": 0x35,
}

# Key code → canonical name, for turning a recorded key back into a string.
VK_NAMES: dict[int, str] = {
    **{vk: ch for ch, vk in CHAR_VKS.items()},
    **{vk: name for name, vk in NAMED_VKS.items() if name != "escape"},
}

# ---------------------------------------------------------------------------
# Accessibility
# ---------------------------------------------------------------------------

def is_trusted() -> bool:
    """True if this process has the Accessibility permission."""
    return bool(AXIsProcessTrusted())


def request_trust() -> bool:
    """Check Accessibility, showing the system prompt if not yet granted."""
    return bool(AXIsProcessTrustedWithOptions({kAXTrustedCheckOptionPrompt: True}))


def can_listen() -> bool:
    """True if this process has Input Monitoring (needed for the hotkey)."""
    return bool(Quartz.CGPreflightListenEventAccess())


def request_listen() -> bool:
    """Check Input Monitoring, showing the system prompt if not yet granted."""
    return bool(Quartz.CGRequestListenEventAccess())


def has_permissions() -> bool:
    """True once both Accessibility and Input Monitoring are granted."""
    return is_trusted() and can_listen()


# ---------------------------------------------------------------------------
# Public API — mirrors win32input.py
# ---------------------------------------------------------------------------

def GetAsyncKeyState(vk: int) -> int:
    """Return 0x8000 if the physical key is down, like the Win32 call."""
    down = Quartz.CGEventSourceKeyState(
        Quartz.kCGEventSourceStateHIDSystemState, vk,
    )
    return 0x8000 if down else 0


def get_foreground_window() -> int:
    """Return the PID of the frontmost application, or 0."""
    app = NSWorkspace.sharedWorkspace().frontmostApplication()
    return app.processIdentifier() if app else 0


def get_clipboard_sequence() -> int:
    """Return the pasteboard change count — bumps on every clipboard change."""
    return NSPasteboard.generalPasteboard().changeCount()


def vk_for_char(char: str) -> int | None:
    """Return the key code for a character on the ANSI layout."""
    return CHAR_VKS.get(char.lower())


def sendinput_combo(modifier_vk: int, key_vk: int) -> int:
    """Post a ⌘+key combo via CGEvent. Returns number of events posted.

    Returns 0 without posting when Accessibility isn't granted — macOS
    would drop the events silently otherwise.
    """
    if not is_trusted():
        return 0

    source = Quartz.CGEventSourceCreate(
        Quartz.kCGEventSourceStateHIDSystemState,
    )
    cmd = Quartz.kCGEventFlagMaskCommand
    events = [
        (modifier_vk, True, cmd),
        (key_vk, True, cmd),
        (key_vk, False, cmd),
        (modifier_vk, False, 0),
    ]
    for vk, down, flags in events:
        event = Quartz.CGEventCreateKeyboardEvent(source, vk, down)
        Quartz.CGEventSetFlags(event, flags)
        Quartz.CGEventPost(Quartz.kCGHIDEventTap, event)
    return len(events)
