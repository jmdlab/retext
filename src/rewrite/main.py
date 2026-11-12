"""Entry point — system-tray icon, global hotkey, and rewrite pipeline."""

from __future__ import annotations

import logging
import sys
import threading
from pathlib import Path

import pystray
from PIL import Image

from rewrite.clipboard import (
    capture_selection,
    replace_selection,
    restore_clipboard,
    save_clipboard,
)
from rewrite.config import load_config
from rewrite.hotkey import HotkeyManager
from rewrite.logviewer import LogViewer, log_buffer
from rewrite.model_updater import ModelUpdater
from rewrite.providers.base import BaseProvider
from rewrite.rewriter import PROVIDER_LABELS, get_provider, rewrite_text
from rewrite.settings import open_settings
from rewrite.startup import refresh as refresh_startup_entry

log = logging.getLogger(__name__)


def _base_path() -> Path:
    """Return the base path for bundled assets (PyInstaller or dev)."""
    if getattr(sys, "_MEIPASS", None):
        return Path(sys._MEIPASS)
    return Path(__file__).parent.parent.parent


ICON_PATH = _base_path() / "assets" / "icon.ico"

_FALLBACK_COLOR = (66, 133, 244, 255)
_FALLBACK_SIZE = 64


def _get_icon_image() -> Image.Image:
    """Load the tray icon, or create a colored-square fallback."""
    if ICON_PATH.exists():
        return Image.open(ICON_PATH)
    return Image.new(
        "RGBA", (_FALLBACK_SIZE, _FALLBACK_SIZE), _FALLBACK_COLOR,
    )


class RewriteApp:
    """Top-level app: tray icon + hotkey + rewrite pipeline."""

    def __init__(self) -> None:
        self.config = load_config()
        self.hotkey_manager = HotkeyManager()
        self.tray: pystray.Icon | None = None
        self._settings_open = False
        self._log_viewer = LogViewer(icon_path=ICON_PATH)
        self._pipeline_lock = threading.Lock()
        self._provider: BaseProvider | None = None
        self._updater: ModelUpdater | None = None

    def _restart_model_updater(self) -> None:
        """(Re)start the Ollama model keeper when Ollama is the provider."""
        if self._updater is not None:
            self._updater.stop()
            self._updater = None
        if self.config.get("provider") != "ollama":
            return
        self._updater = ModelUpdater(
            model=self.config["ollama_model"],
            url=self.config["ollama_url"],
            auto_update=self.config.get("ollama_auto_update", True),
            report=log_buffer.append,
        )
        self._updater.start()

    def _get_provider(self) -> BaseProvider:
        """Return the cached provider, creating it on first use.

        Reusing the provider keeps the HTTP connection alive between
        rewrites; the cache is invalidated when settings change.
        """
        if self._provider is None:
            self._provider = get_provider(self.config)
        return self._provider

    # ------------------------------------------------------------------
    # Tray tooltip helper
    # ------------------------------------------------------------------

    def _set_status(self, status: str) -> None:
        """Update the tray tooltip with a status message."""
        if self.tray:
            self.tray.title = f"Retext — {status}"

    # ------------------------------------------------------------------
    # Rewrite pipeline
    # ------------------------------------------------------------------

    def _on_rewrite(self) -> None:
        """Hotkey callback — already invoked on a daemon thread by HotkeyManager."""
        self._rewrite_pipeline()

    def _rewrite_pipeline(self) -> None:
        """Capture -> rewrite -> paste -> restore clipboard."""
        if not self._pipeline_lock.acquire(blocking=False):
            log_buffer.append("Hotkey triggered — pipeline busy, skipped")
            return
        try:
            self._run_pipeline()
        finally:
            self._pipeline_lock.release()

    def _run_pipeline(self) -> None:
        log_buffer.append("Hotkey triggered")
        self._set_status("Capturing…")

        original_clipboard = save_clipboard()
        try:
            text = capture_selection()
            if not text:
                log_buffer.append("No text selected — skipped")
                self._set_status("Ready")
                return

            preview = text[:60].replace("\n", " ")
            log_buffer.append(f"Captured {len(text)} chars: \"{preview}\"")
            self._set_status("Rewriting…")
            provider = self.config.get("provider", "gemini")
            label = PROVIDER_LABELS.get(provider, provider)
            model = self.config.get(f"{provider}_model", "")
            log_buffer.append(f"Sending to {label} ({model})…")

            corrected = rewrite_text(text, self._get_provider())

            if corrected and corrected != text:
                replace_selection(corrected)
                log_buffer.append(
                    f"Done — replaced ({len(text)} → {len(corrected)} chars)",
                )
                self._set_status("Done!")
            else:
                log_buffer.append("No changes needed")
                self._set_status("Ready")
        except Exception as exc:
            log_buffer.append(f"Error: {exc}")
            self._set_status("Error")
            log.exception("Pipeline error")
        finally:
            restore_clipboard(original_clipboard)

    # ------------------------------------------------------------------
    # Log viewer
    # ------------------------------------------------------------------

    def _on_show_log(
        self,
        icon: pystray.Icon | None = None,
        item: pystray.MenuItem | None = None,
    ) -> None:
        """Open the log viewer window."""
        if self._log_viewer.is_open:
            return
        threading.Thread(
            target=self._log_viewer.show, daemon=True,
        ).start()

    # ------------------------------------------------------------------
    # Settings
    # ------------------------------------------------------------------

    def _on_settings(
        self,
        icon: pystray.Icon | None = None,
        item: pystray.MenuItem | None = None,
    ) -> None:
        """Open the settings window (once at a time)."""
        if self._settings_open:
            return
        self._settings_open = True

        def _on_save(new_config: dict) -> None:
            self.config = new_config
            self._provider = None  # provider, key or model may have changed
            self.hotkey_manager.register(
                self.config["hotkey"], self._on_rewrite,
            )
            self._restart_model_updater()

        def _run() -> None:
            try:
                open_settings(on_save=_on_save, icon_path=ICON_PATH)
            finally:
                self._settings_open = False

        threading.Thread(target=_run, daemon=True).start()

    # ------------------------------------------------------------------
    # Quit
    # ------------------------------------------------------------------

    def _on_quit(
        self,
        icon: pystray.Icon | None = None,
        item: pystray.MenuItem | None = None,
    ) -> None:
        """Tear down hotkey listener and stop the tray icon."""
        self.hotkey_manager.unregister()
        if self._updater is not None:
            self._updater.stop()
        if self.tray:
            self.tray.stop()

    # ------------------------------------------------------------------
    # Run
    # ------------------------------------------------------------------

    def run(self) -> None:
        """Register hotkey, build tray icon, enter event loop."""
        self.hotkey_manager.register(
            self.config["hotkey"], self._on_rewrite,
        )

        log_buffer.append(f"Started — hotkey: {self.config['hotkey']}")
        self._restart_model_updater()

        menu = pystray.Menu(
            pystray.MenuItem(
                "Rewrite Selection", self._on_rewrite, default=True,
            ),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem("Show Log", self._on_show_log),
            pystray.MenuItem("Settings\u2026", self._on_settings),
            pystray.MenuItem("Quit", self._on_quit),
        )

        self.tray = pystray.Icon(
            name="Retext",
            icon=_get_icon_image(),
            title="Retext — Ready",
            menu=menu,
        )
        self.tray.run()


def main() -> None:
    """CLI entry point (``rewrite`` command via pyproject.toml)."""
    logging.basicConfig(
        level=logging.WARNING,
        format="%(asctime)s [%(name)s] %(message)s",
        datefmt="%H:%M:%S",
    )
    refresh_startup_entry()
    app = RewriteApp()
    app.run()


if __name__ == "__main__":
    main()
