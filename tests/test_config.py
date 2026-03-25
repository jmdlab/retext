import json

from rewrite.config import DEFAULT_CONFIG, load_config, save_config


def test_default_config_returned_when_no_file(temp_config_dir):
    config = load_config()
    expected = {**DEFAULT_CONFIG, "gemini_api_key": ""}
    assert config == expected


def test_save_and_load_roundtrip(temp_config_dir, sample_config):
    save_config(sample_config)
    loaded = load_config()
    assert loaded == sample_config


def test_missing_keys_filled_with_defaults(temp_config_dir):
    """If config file has fewer keys than defaults, missing keys get default values."""
    partial = {"gemini_api_key": "my-key"}
    save_config(partial)
    loaded = load_config()
    assert loaded["gemini_api_key"] == "my-key"
    assert loaded["hotkey"] == DEFAULT_CONFIG["hotkey"]
    assert loaded["gemini_model"] == DEFAULT_CONFIG["gemini_model"]


def test_config_dir_created(tmp_path):
    import os
    from unittest.mock import patch

    with patch.dict(os.environ, {"APPDATA": str(tmp_path / "subdir")}):
        from rewrite import config

        result = config.get_config_dir()
        assert result.exists()


def test_save_creates_file(temp_config_dir, sample_config):
    save_config(sample_config)
    config_file = temp_config_dir / "config.json"
    assert config_file.exists()
    data = json.loads(config_file.read_text())
    # API key should NOT be in the JSON file
    assert "gemini_api_key" not in data


def test_api_key_not_in_json(temp_config_dir, sample_config):
    """API key must be stored in keyring, not in config.json."""
    save_config(sample_config)
    config_file = temp_config_dir / "config.json"
    data = json.loads(config_file.read_text())
    assert "gemini_api_key" not in data


def test_api_key_survives_roundtrip(temp_config_dir):
    """API key set via save_config should come back via load_config."""
    save_config({"gemini_api_key": "secret-key-123"})
    loaded = load_config()
    assert loaded["gemini_api_key"] == "secret-key-123"


def test_migrate_plaintext_key(temp_config_dir):
    """If config.json contains a plaintext API key, it gets migrated to keyring."""
    config_file = temp_config_dir / "config.json"
    config_file.write_text(json.dumps({
        "hotkey": "ctrl+alt+r",
        "gemini_api_key": "old-plaintext-key",
        "gemini_model": "gemini-2.5-flash",
    }))
    loaded = load_config()
    # Key should be migrated
    assert loaded["gemini_api_key"] == "old-plaintext-key"
    # JSON file should no longer contain the key
    data = json.loads(config_file.read_text())
    assert "gemini_api_key" not in data
