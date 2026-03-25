from unittest.mock import patch

import pytest


@pytest.fixture
def temp_config_dir(tmp_path):
    """Provide a temp directory for config files and mock keyring."""
    store: dict[str, str] = {}

    def _get(service: str, account: str) -> str | None:
        return store.get(f"{service}:{account}")

    def _set(service: str, account: str, password: str) -> None:
        store[f"{service}:{account}"] = password

    def _delete(service: str, account: str) -> None:
        key = f"{service}:{account}"
        if key in store:
            del store[key]
        else:
            import keyring.errors
            raise keyring.errors.PasswordDeleteError(f"{key} not found")

    with (
        patch("rewrite.config.get_config_dir", return_value=tmp_path),
        patch("rewrite.config.keyring.get_password", side_effect=_get),
        patch("rewrite.config.keyring.set_password", side_effect=_set),
        patch("rewrite.config.keyring.delete_password", side_effect=_delete),
    ):
        yield tmp_path


@pytest.fixture
def sample_config():
    """Return a sample config dict."""
    return {
        "hotkey": "ctrl+shift+r",
        "gemini_api_key": "test-gemini-key",
        "gemini_model": "gemini-2.5-flash",
    }
