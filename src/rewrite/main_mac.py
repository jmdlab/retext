"""macOS entry point — menu bar icon, global hotkey, and rewrite pipeline."""

from __future__ import annotations

import logging
import plistlib
import re
import subprocess
import sys
import threading
from pathlib import Path

import rumps
from AppKit import NSApp
from pynput import keyboard
from PyObjCTools.AppHelper import callAfter

from rewrite import macinput
from rewrite.config import DEFAULT_CONFIG, load_config, save_config
from rewrite.hotkey import (
    _KEY_TO_MOD,
    HotkeyManager,
    format_hotkey_mac,
    hotkey_string,
    key_name_for_vk,
)
from rewrite.logbuffer import log_buffer
from rewrite.pipeline import run_rewrite
from rewrite.providers.base import BaseProvider
from rewrite.rewriter import get_provider

log = logging.getLogger(__name__)

BUNDLE_ID = "com.jmdlab.retext"
LOG_PATH = Path.home() / "Library" / "Logs" / "Retext" / "retext.log"
LAUNCH_AGENT_PATH = Path.home() / "Library" / "LaunchAgents" / f"{BUNDLE_ID}.plist"
ACCESSIBILITY_URL = (
    "x-apple.systempreferences:com.apple.preference.security?Privacy_Accessibility"
)
INPUT_MONITORING_URL = (
    "x-apple.systempreferences:com.apple.preference.security?Privacy_ListenEvent"
)

_WORKING_STATUSES = {"Capturing…", "Rewriting…"}
_FKEY = re.compile(r"f\d+")
# Shortcuts the recorder refuses — ⌘C/⌘V would re-trigger on Retext's own paste.
_RESERVED_HOTKEYS = {"cmd+c", "cmd+v", "cmd+x", "cmd+q", "cmd+a", "cmd+z"}


def _base_path() -> Path:
    """Return the base path for bundled assets (PyInstaller or dev)."""
    if getattr(sys, "_MEIPASS", None):
        return Path(sys._MEIPASS)
    return Path(__file__).parent.parent.parent


def _app_bundle() -> Path | None:
    """Return the enclosing Retext.app when running bundled, else None."""
    if not getattr(sys, "frozen", False):
        return None
    # Retext.app/Contents/MacOS/Retext
    return Path(sys.executable).resolve().parents[2]


MENUBAR_ICON = _base_path() / "assets" / "menubar.png"


def _write_log_line(ts, msg: str) -> None:
    with LOG_PATH.open("a", encoding="utf-8") as f:
        f.write(f"{ts:%Y-%m-%d %H:%M:%S}  {msg}\n")


def _prompt(
    title: str, message: str, default: str = "", *, secure: bool = False,
) -> str | None:
    """Show a native text-input dialog. Returns the text, or None on cancel."""
    # Menu bar apps aren't frontmost by default — bring the dialog forward.
    NSApp.activateIgnoringOtherApps_(True)
    response = rumps.Window(
        message=message,
        title=title,
        default_text=default,
        ok="Save",
        cancel="Cancel",
        dimensions=(320, 24),
        secure=secure,
    ).run()
    return response.text.strip() if response.clicked else None


class RetextMenuBarApp(rumps.App):
    """Menu bar app: status item + hotkey + rewrite pipeline."""

    def __init__(self) -> None:
        super().__init__(
            "Retext",
            icon=str(MENUBAR_ICON) if MENUBAR_ICON.exists() else None,
            template=True,
            quit_button=None,
        )
        self.config = load_config()
        self.hotkey_manager = HotkeyManager()
        self._pipeline_lock = threading.Lock()
        self._provider: BaseProvider | None = None
        self._recorder: keyboard.Listener | None = None
        self._record_timeout: rumps.Timer | None = None
        self._had_permissions = macinput.has_permissions()

        self._status_item = rumps.MenuItem("Ready")
        self._rewrite_item = rumps.MenuItem(
            "Rewrite Selection", callback=self._on_rewrite_click,
        )
        self._permission_item = rumps.MenuItem(
            "Grant Permissions…", callback=self._on_permission,
        )
        self._hotkey_item = rumps.MenuItem("Hotkey", callback=self._on_record_hotkey)
        self._key_item = rumps.MenuItem("API Key", callback=self._on_api_key)
        self._model_item = rumps.MenuItem("Model", callback=self._on_model)
        self._login_item = rumps.MenuItem(
            "Launch at Login", callback=self._on_toggle_login,
        )
        self.menu = [
            self._status_item,
            self._rewrite_item,
            self._permission_item,
            None,
            self._hotkey_item,
            self._key_item,
            self._model_item,
            None,
            rumps.MenuItem("Show Log", callback=self._on_show_log),
            self._login_item,
            rumps.MenuItem("Quit Retext", callback=self._on_quit, key="q"),
        ]
        self._refresh_menu()

    # ------------------------------------------------------------------
    # Menu state
    # ------------------------------------------------------------------

    def _refresh_menu(self) -> None:
        hotkey = format_hotkey_mac(self.config["hotkey"])
        self._rewrite_item.title = f"Rewrite Selection   {hotkey}"
        self._hotkey_item.title = f"Hotkey: {hotkey} — Record New…"
        has_key = bool(self.config.get("gemini_api_key"))
        self._key_item.title = (
            "Gemini API Key… (set)" if has_key else "Set Gemini API Key…"
        )
        self._model_item.title = f"Model: {self.config['gemini_model']}…"
        self._login_item.state = LAUNCH_AGENT_PATH.exists()
        self._check_permission()

    def _check_permission(self, _timer: rumps.Timer | None = None) -> None:
        """Show the permission item only while a permission is missing.

        A pynput listener started without Input Monitoring never receives
        events, so re-register the hotkey once access is granted.
        """
        granted = macinput.has_permissions()
        if granted and not self._had_permissions and self._recorder is None:
            log_buffer.append("Permissions granted — hotkey re-registered")
            self._register_hotkey()
        self._had_permissions = granted
        if granted:
            self._permission_item.hide()
        else:
            self._permission_item.show()

    def _set_status(self, status: str) -> None:
        """Thread-safe status update: menu text + a working indicator."""
        def _apply() -> None:
            self._status_item.title = status
            idle = None if MENUBAR_ICON.exists() else "Retext"
            self.title = " …" if status in _WORKING_STATUSES else idle
            if status == "Error":
                self.title = " !"
        callAfter(_apply)

    # ------------------------------------------------------------------
    # Rewrite pipeline
    # ------------------------------------------------------------------

    def _get_provider(self) -> BaseProvider:
        if self._provider is None:
            self._provider = get_provider(self.config)
        return self._provider

    def _on_rewrite(self) -> None:
        """Hotkey callback — already invoked on a daemon thread by HotkeyManager."""
        if not self._pipeline_lock.acquire(blocking=False):
            log_buffer.append("Hotkey triggered — pipeline busy, skipped")
            return
        try:
            if not macinput.is_trusted():
                log_buffer.append(
                    "Error: Accessibility not granted — can't send ⌘C/⌘V",
                )
                self._set_status("Error")
                return
            run_rewrite(self._get_provider, self._set_status)
        finally:
            self._pipeline_lock.release()

    def _on_rewrite_click(self, _sender: rumps.MenuItem) -> None:
        threading.Thread(target=self._on_rewrite, daemon=True).start()

    def _register_hotkey(self) -> None:
        try:
            self.hotkey_manager.register(self.config["hotkey"], self._on_rewrite)
        except ValueError as exc:
            log_buffer.append(f"Error: {exc} — falling back to default")
            self.config["hotkey"] = DEFAULT_CONFIG["hotkey"]
            self.hotkey_manager.register(self.config["hotkey"], self._on_rewrite)

    # ------------------------------------------------------------------
    # Settings
    # ------------------------------------------------------------------

    def _save(self) -> None:
        save_config(self.config)
        self._provider = None  # API key or model may have changed
        self._refresh_menu()

    def _on_api_key(self, _sender: rumps.MenuItem) -> None:
        key = _prompt(
            "Gemini API Key",
            "Paste your key from aistudio.google.com/apikey.\n"
            "It's stored in your macOS Keychain.",
            secure=True,
        )
        if key is None:
            return
        self.config["gemini_api_key"] = key
        self._save()
        log_buffer.append("API key updated" if key else "API key cleared")

    def _on_model(self, _sender: rumps.MenuItem) -> None:
        model = _prompt(
            "Gemini Model",
            "Any Gemini model name.",
            default=self.config["gemini_model"],
        )
        if not model:
            return
        self.config["gemini_model"] = model
        self._save()
        log_buffer.append(f"Model set to {model}")

    def _on_record_hotkey(self, _sender: rumps.MenuItem) -> None:
        """Capture the next modifier+key combo as the new hotkey.

        Esc, clicking the item again, or 10 s of inactivity cancels.
        """
        if self._recorder is not None:
            self._cancel_recording()
            return
        self.hotkey_manager.unregister()
        self._hotkey_item.title = "Press new hotkey…  (Esc or click to cancel)"
        mods: set[str] = set()

        def _finish(hotkey: str | None) -> None:
            if self._recorder is None:
                return  # already finished (timeout vs keypress race)
            self._recorder.stop()
            self._recorder = None
            if self._record_timeout is not None:
                self._record_timeout.stop()
                self._record_timeout = None
            if hotkey:
                self.config["hotkey"] = hotkey
                self._save()
                log_buffer.append(f"Hotkey set to {hotkey}")
            self._register_hotkey()
            self._refresh_menu()

        def _on_press(key: keyboard.Key | keyboard.KeyCode | None) -> bool | None:
            if key is None:
                return None
            if isinstance(key, keyboard.Key):
                mod = _KEY_TO_MOD.get(key)
                if mod:
                    mods.add(mod)
                    return None
                if key == keyboard.Key.esc:
                    callAfter(_finish, None)
                    return False
                vk = key.value.vk
            else:
                vk = key.vk
            name = key_name_for_vk(vk) if vk is not None else None
            # Require a modifier unless it's a function key — a bare letter
            # would hijack normal typing.
            if name is None or (mods <= {"shift"} and not _FKEY.fullmatch(name)):
                return None
            hotkey = hotkey_string(mods, name)
            if hotkey in _RESERVED_HOTKEYS:
                return None
            callAfter(_finish, hotkey)
            return False

        def _on_release(key: keyboard.Key | keyboard.KeyCode | None) -> None:
            if isinstance(key, keyboard.Key):
                mods.discard(_KEY_TO_MOD.get(key, ""))

        self._recorder = keyboard.Listener(
            on_press=_on_press, on_release=_on_release,
        )
        self._recorder.daemon = True
        self._recorder.start()
        self._finish_recording = _finish
        self._record_timeout = rumps.Timer(
            lambda _t: self._cancel_recording(), 10,
        )
        self._record_timeout.start()

    def _cancel_recording(self) -> None:
        log_buffer.append("Hotkey recording cancelled")
        self._finish_recording(None)

    def _on_permission(self, _sender: rumps.MenuItem) -> None:
        macinput.request_listen()
        url = ACCESSIBILITY_URL if not macinput.is_trusted() else INPUT_MONITORING_URL
        if not macinput.request_trust() or not macinput.can_listen():
            subprocess.run(["/usr/bin/open", url], check=False)

    def _on_toggle_login(self, _sender: rumps.MenuItem) -> None:
        app = _app_bundle()
        if app is None or not str(app).startswith("/Applications/"):
            log_buffer.append("Launch at Login needs Retext.app in /Applications")
            return
        if LAUNCH_AGENT_PATH.exists():
            LAUNCH_AGENT_PATH.unlink()
            log_buffer.append("Launch at Login disabled")
        else:
            LAUNCH_AGENT_PATH.parent.mkdir(parents=True, exist_ok=True)
            with LAUNCH_AGENT_PATH.open("wb") as f:
                plistlib.dump({
                    "Label": BUNDLE_ID,
                    "ProgramArguments": ["/usr/bin/open", "-a", str(app)],
                    "RunAtLoad": True,
                }, f)
            log_buffer.append("Launch at Login enabled")
        self._refresh_menu()

    # ------------------------------------------------------------------
    # Log / quit
    # ------------------------------------------------------------------

    def _on_show_log(self, _sender: rumps.MenuItem) -> None:
        LOG_PATH.touch(exist_ok=True)
        subprocess.run(["/usr/bin/open", "-a", "Console", str(LOG_PATH)], check=False)

    def _on_quit(self, _sender: rumps.MenuItem) -> None:
        self.hotkey_manager.unregister()
        rumps.quit_application()

    # ------------------------------------------------------------------
    # Run
    # ------------------------------------------------------------------

    def start(self) -> None:
        """Check permissions, register the hotkey, enter the run loop."""
        if not macinput.request_trust():
            log_buffer.append(
                "Accessibility not granted — enable Retext in System Settings "
                "→ Privacy & Security → Accessibility",
            )
        if not macinput.request_listen():
            log_buffer.append(
                "Input Monitoring not granted — enable Retext in System Settings "
                "→ Privacy & Security → Input Monitoring",
            )
        self._register_hotkey()
        self._refresh_menu()
        log_buffer.append(f"Started — hotkey: {self.config['hotkey']}")

        # Re-check permissions periodically so the warning item disappears
        # and the hotkey starts working once the user grants access.
        rumps.Timer(self._check_permission, 5).start()
        self.run()


def main() -> None:
    """Entry point for the macOS menu bar app."""
    logging.basicConfig(
        level=logging.WARNING,
        format="%(asctime)s [%(name)s] %(message)s",
        datefmt="%H:%M:%S",
    )
    LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    log_buffer.on_entry(_write_log_line)
    RetextMenuBarApp().start()


if __name__ == "__main__":
    main()
