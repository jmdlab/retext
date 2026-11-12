import pytest

from rewrite.settings import format_hotkey


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("ctrl+alt+r", "Ctrl + Alt + R"),
        ("ctrl+shift+f12", "Ctrl + Shift + F12"),
        ("win+page_up", "Win + Page Up"),
        ("…", "…"),
        ("", ""),
    ],
)
def test_format_hotkey(raw, expected):
    assert format_hotkey(raw) == expected
