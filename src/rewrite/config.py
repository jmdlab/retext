"""Configuration management — JSON config + OS credential store."""

from __future__ import annotations

import json
import logging
import os
from pathlib import Path

import keyring

log = logging.getLogger(__name__)

SERVICE_NAME = "retext"
KEY_ACCOUNT = "gemini_api_key"

DEFAULT_CONFIG: dict = {
    "hotkey": "ctrl+alt+r",
    "gemini_model": "gemini-2.5-flash",
}


def get_config_dir() -> Path:
    """Return %APPDATA%/Retext/, creating it if it doesn't exist."""
    appdata = os.environ.get("APPDATA")
    if not appdata:
        raise RuntimeError("%APPDATA% environment variable is not set")
    config_dir = Path(appdata) / "Retext"
    config_dir.mkdir(parents=True, exist_ok=True)
    return config_dir


def get_config_path() -> Path:
    """Return the full path to config.json."""
    return get_config_dir() / "config.json"


# ------------------------------------------------------------------
# API key — stored in OS credential manager via keyring
# ------------------------------------------------------------------


def get_api_key() -> str:
    """Retrieve the Gemini API key from the OS credential store."""
    return keyring.get_password(SERVICE_NAME, KEY_ACCOUNT) or ""


def set_api_key(api_key: str) -> None:
    """Store the Gemini API key in the OS credential store."""
    if api_key:
        keyring.set_password(SERVICE_NAME, KEY_ACCOUNT, api_key)
    else:
        with _suppress_keyring_errors():
            keyring.delete_password(SERVICE_NAME, KEY_ACCOUNT)


def _suppress_keyring_errors():
    """Context manager that swallows keyring errors (e.g. deleting a missing key)."""
    import contextlib
    return contextlib.suppress(keyring.errors.PasswordDeleteError)


# ------------------------------------------------------------------
# General config — everything except the API key
# ------------------------------------------------------------------


def load_config() -> dict:
    """Load config from disk, merging with defaults so new keys always exist.

    The API key is read from the OS credential store and injected into the
    returned dict for backward-compatible consumption by the rest of the app.
    """
    path = get_config_path()
    config = dict(DEFAULT_CONFIG)
    if path.exists():
        with path.open("r", encoding="utf-8") as f:
            stored = json.load(f)

        # Migrate: move plaintext API key to credential store
        if "gemini_api_key" in stored:
            plaintext_key = stored.pop("gemini_api_key", "")
            if plaintext_key and not get_api_key():
                log.info("Migrating API key from config.json to credential store")
                set_api_key(plaintext_key)
            # Re-save config.json without the key
            _write_json(path, stored)

        config.update(stored)

    # Inject the key from the credential store so callers see it in the dict
    config["gemini_api_key"] = get_api_key()
    return config


def save_config(config: dict) -> None:
    """Write config dict to disk. The API key goes to the credential store."""
    api_key = config.pop("gemini_api_key", None)
    if api_key is not None:
        set_api_key(api_key)

    path = get_config_path()
    _write_json(path, config)

    # Restore the key in the dict so the caller's reference stays complete
    if api_key is not None:
        config["gemini_api_key"] = api_key


def _write_json(path: Path, data: dict) -> None:
    """Write a dict to a JSON file."""
    with path.open("w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
