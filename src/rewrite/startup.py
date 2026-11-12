"""Launch-at-startup management — HKCU Run registry key."""

from __future__ import annotations

import logging
import sys
import winreg
from pathlib import Path

log = logging.getLogger(__name__)

RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"
APP_NAME = "Retext"


def _launch_command() -> str:
    """Return the command Windows should run at login.

    Frozen (PyInstaller): the bundled exe itself. Dev: the current
    interpreter's pythonw running the package, so no console window opens.
    """
    if getattr(sys, "frozen", False):
        return f'"{sys.executable}"'

    interpreter = Path(sys.executable)
    pythonw = interpreter.with_name("pythonw.exe")
    if pythonw.exists():
        interpreter = pythonw
    return f'"{interpreter}" -m rewrite.main'


def is_enabled() -> bool:
    """Return True if a Retext entry exists in the user's Run key."""
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY) as key:
            winreg.QueryValueEx(key, APP_NAME)
        return True
    except OSError:
        return False


def set_enabled(enabled: bool) -> None:
    """Add or remove the Retext entry in the user's Run key."""
    if enabled:
        with winreg.OpenKey(
            winreg.HKEY_CURRENT_USER, RUN_KEY, 0, winreg.KEY_SET_VALUE,
        ) as key:
            winreg.SetValueEx(
                key, APP_NAME, 0, winreg.REG_SZ, _launch_command(),
            )
        log.info("Startup entry set: %s", _launch_command())
    else:
        try:
            with winreg.OpenKey(
                winreg.HKEY_CURRENT_USER, RUN_KEY, 0, winreg.KEY_SET_VALUE,
            ) as key:
                winreg.DeleteValue(key, APP_NAME)
            log.info("Startup entry removed")
        except OSError:
            pass  # already absent


def refresh() -> None:
    """If startup is enabled, rewrite the entry so it tracks the current
    executable path (the exe may have been moved or rebuilt elsewhere)."""
    if is_enabled():
        set_enabled(True)
