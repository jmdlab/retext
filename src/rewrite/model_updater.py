"""Background keeper for the local Ollama model: pull updates, preload."""

from __future__ import annotations

import logging
import threading
from collections.abc import Callable

from rewrite.providers import ollama

log = logging.getLogger(__name__)

UPDATE_INTERVAL_S = 24 * 60 * 60


class ModelUpdater:
    """Pulls the configured model at start and then daily, then preloads it.

    ``ollama pull`` on an up-to-date tag only compares manifests, so the
    daily check is cheap; when the tag moved upstream the new weights are
    downloaded and used from the next rewrite on.
    """

    def __init__(
        self,
        model: str,
        url: str,
        auto_update: bool,
        report: Callable[[str], None],
        interval_s: float = UPDATE_INTERVAL_S,
    ) -> None:
        self.model = model
        self.url = url
        self.auto_update = auto_update
        self.report = report
        self.interval_s = interval_s
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()

    def _loop(self) -> None:
        self.run_once()
        while self.auto_update and not self._stop.wait(self.interval_s):
            self.run_once()

    def run_once(self) -> None:
        """Pull if needed, then preload. Never raises — failures are reported."""
        try:
            ollama.ensure_running(self.url)
            installed = ollama.list_models(self.url)
            missing = self.model not in installed
            if missing or self.auto_update:
                verb = "Downloading" if missing else "Checking for updates to"
                self.report(f"Ollama: {verb} {self.model}…")
                status = ollama.pull_model(self.model, self.url)
                self.report(f"Ollama: {self.model} {status or 'pulled'}")
            ollama.preload_model(self.model, self.url)
            self.report(f"Ollama: {self.model} ready")
        except ollama.OllamaError as exc:
            self.report(f"Ollama: {exc}")
            log.warning("Model update failed: %s", exc)
