"""Local Ollama provider — talks to the Ollama HTTP API with the stdlib."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

from rewrite.providers.base import BaseProvider

DEFAULT_URL = "http://127.0.0.1:11434"
DEFAULT_MODEL = "gemma4:e4b"
REQUEST_TIMEOUT_S = 60
PULL_TIMEOUT_S = 3600
START_TIMEOUT_S = 15
# Keep the model in VRAM between rewrites; reloading costs several seconds.
KEEP_ALIVE = "30m"


class OllamaError(RuntimeError):
    """Raised when the Ollama server is unreachable or returns an error."""


def _request(
    url: str, path: str, payload: dict[str, Any] | None = None,
    timeout: float = REQUEST_TIMEOUT_S,
) -> dict[str, Any]:
    """POST ``payload`` (or GET when None) to the Ollama API and decode JSON."""
    data = json.dumps(payload).encode() if payload is not None else None
    req = urllib.request.Request(
        url.rstrip("/") + path,
        data=data,
        headers={"Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.load(resp)
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode(errors="replace")
        raise OllamaError(f"Ollama {exc.code}: {detail}") from exc
    except (urllib.error.URLError, TimeoutError, ConnectionError) as exc:
        raise OllamaError(
            f"Ollama is not reachable at {url} — is it running? ({exc})",
        ) from exc


def _find_executable() -> str | None:
    """Locate ollama.exe on PATH or in its default per-user install dir."""
    found = shutil.which("ollama")
    if found:
        return found
    local = os.environ.get("LOCALAPPDATA")
    if local:
        candidate = Path(local) / "Programs" / "Ollama" / "ollama.exe"
        if candidate.exists():
            return str(candidate)
    return None


def is_running(url: str = DEFAULT_URL) -> bool:
    try:
        _request(url, "/api/version", timeout=2)
    except OllamaError:
        return False
    return True


def ensure_running(url: str = DEFAULT_URL) -> None:
    """Start ``ollama serve`` in the background if the server is down.

    Raises OllamaError when Ollama isn't installed or doesn't come up.
    """
    if is_running(url):
        return
    exe = _find_executable()
    if exe is None:
        raise OllamaError("Ollama is not installed — get it at ollama.com.")
    subprocess.Popen(
        [exe, "serve"],
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
    )
    deadline = time.monotonic() + START_TIMEOUT_S
    while time.monotonic() < deadline:
        if is_running(url):
            return
        time.sleep(0.25)
    raise OllamaError(f"Ollama did not start within {START_TIMEOUT_S}s.")


def list_models(url: str = DEFAULT_URL) -> list[str]:
    """Return the names of models installed locally, sorted."""
    tags = _request(url, "/api/tags", timeout=5)
    return sorted(m["name"] for m in tags.get("models", []))


def pull_model(model: str, url: str = DEFAULT_URL) -> str:
    """Download or update ``model``. Only changed layers are fetched.

    Returns the final status reported by Ollama (normally ``"success"``).
    """
    result = _request(
        url, "/api/pull", {"model": model, "stream": False},
        timeout=PULL_TIMEOUT_S,
    )
    return str(result.get("status", ""))


def preload_model(model: str, url: str = DEFAULT_URL) -> None:
    """Load ``model`` into memory so the first rewrite is instant."""
    _request(
        url, "/api/generate", {"model": model, "keep_alive": KEEP_ALIVE},
    )


class OllamaProvider(BaseProvider):
    """Rewrites text with a model served by a local Ollama instance."""

    def __init__(self, model: str = DEFAULT_MODEL, url: str = DEFAULT_URL) -> None:
        if not model:
            raise ValueError("Ollama model not configured. Please set it in Settings.")
        self.model = model
        self.url = url

    def rewrite(self, text: str, system_prompt: str = "") -> str:
        ensure_running(self.url)
        response = _request(self.url, "/api/chat", {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": text},
            ],
            "stream": False,
            "think": False,
            "keep_alive": KEEP_ALIVE,
            "options": {"temperature": 0.1},
        })
        content = response.get("message", {}).get("content", "")
        return content or text
