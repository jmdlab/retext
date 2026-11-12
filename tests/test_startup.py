"""Tests for launch-at-startup registry management."""

from __future__ import annotations

import sys

import pytest

from rewrite import startup


def test_launch_command_frozen(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "executable", r"D:\Apps\Retext.exe")
    assert startup._launch_command() == '"D:\\Apps\\Retext.exe"'


def test_launch_command_dev(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delattr(sys, "frozen", raising=False)
    command = startup._launch_command()
    assert command.endswith(' -m rewrite.main')
    assert command.startswith('"')


def test_enable_disable_roundtrip(monkeypatch: pytest.MonkeyPatch) -> None:
    """Round-trip against the real HKCU Run key, under a test-only name."""
    monkeypatch.setattr(startup, "APP_NAME", "RetextStartupTest")
    try:
        startup.set_enabled(True)
        assert startup.is_enabled()
        startup.set_enabled(False)
        assert not startup.is_enabled()
        # Disabling when already absent must not raise
        startup.set_enabled(False)
    finally:
        startup.set_enabled(False)
