import sys

import pytest

from rewrite.hotkey import (
    _parse_hotkey,
    _vk_for_key,
    format_hotkey_mac,
    hotkey_string,
)

IS_MAC = sys.platform == "darwin"
windows_only = pytest.mark.skipif(IS_MAC, reason="Windows VK codes")
mac_only = pytest.mark.skipif(not IS_MAC, reason="macOS key codes")


@windows_only
class TestParseHotkey:
    def test_default_hotkey(self):
        mods, vk = _parse_hotkey("ctrl+alt+r")
        assert mods == {"ctrl", "alt"}
        assert vk == ord("R")

    def test_case_and_whitespace_insensitive(self):
        mods, vk = _parse_hotkey(" Ctrl + Alt + R ")
        assert mods == {"ctrl", "alt"}
        assert vk == ord("R")

    def test_function_key(self):
        mods, vk = _parse_hotkey("ctrl+f9")
        assert mods == {"ctrl"}
        assert vk == 0x78

    def test_f12(self):
        _, vk = _parse_hotkey("alt+f12")
        assert vk == 0x7B

    def test_named_key(self):
        mods, vk = _parse_hotkey("ctrl+shift+space")
        assert mods == {"ctrl", "shift"}
        assert vk == 0x20

    def test_digit(self):
        _, vk = _parse_hotkey("win+1")
        assert vk == ord("1")

    def test_unsupported_key_raises(self):
        with pytest.raises(ValueError, match="Unsupported key"):
            _parse_hotkey("ctrl+florp")

    def test_modifiers_only_raises(self):
        with pytest.raises(ValueError, match="No trigger key"):
            _parse_hotkey("ctrl+shift")


@windows_only
class TestVkForKey:
    def test_letter(self):
        assert _vk_for_key("r") == ord("R")

    def test_function_keys_all(self):
        for i in range(1, 25):
            assert _vk_for_key(f"f{i}") == 0x6F + i

    def test_punctuation_resolves_or_none(self):
        # Layout-dependent — must not crash, returns an int VK or None
        result = _vk_for_key(",")
        assert result is None or isinstance(result, int)

    def test_multichar_garbage_is_none(self):
        assert _vk_for_key("florp") is None


@mac_only
class TestParseHotkeyMac:
    def test_default_hotkey(self):
        mods, vk = _parse_hotkey("ctrl+alt+r")
        assert mods == {"ctrl", "alt"}
        assert vk == 0x0F  # kVK_ANSI_R

    def test_mac_aliases(self):
        mods, vk = _parse_hotkey("cmd+option+control+r")
        assert mods == {"win", "alt", "ctrl"}
        assert vk == 0x0F

    def test_function_key(self):
        _, vk = _parse_hotkey("ctrl+f9")
        assert vk == 0x65

    def test_digit_and_punctuation(self):
        assert _vk_for_key("1") == 0x12
        assert _vk_for_key(",") == 0x2B

    def test_named_key(self):
        _, vk = _parse_hotkey("cmd+shift+space")
        assert vk == 0x31

    def test_unsupported_key_raises(self):
        with pytest.raises(ValueError, match="Unsupported key"):
            _parse_hotkey("ctrl+florp")


class TestFormatHotkeyMac:
    def test_default(self):
        assert format_hotkey_mac("ctrl+alt+r") == "\u2303\u2325R"

    def test_hig_modifier_order(self):
        assert format_hotkey_mac("cmd+shift+alt+ctrl+k") == "\u2303\u2325\u21e7\u2318K"

    def test_named_and_function_keys(self):
        assert format_hotkey_mac("ctrl+space") == "\u2303Space"
        assert format_hotkey_mac("f5") == "F5"


class TestHotkeyString:
    def test_canonical_order(self):
        result = hotkey_string({"shift", "ctrl"}, "r")
        assert result == "ctrl+shift+r"

    def test_command_spelling(self):
        expected = "alt+cmd+k" if IS_MAC else "alt+win+k"
        assert hotkey_string({"win", "alt"}, "k") == expected

    def test_roundtrips_through_parser(self):
        mods, _ = _parse_hotkey(hotkey_string({"win", "ctrl"}, "r"))
        assert mods == {"win", "ctrl"}


class TestListenerLiveness:
    def test_not_listening_before_register(self):
        from rewrite.hotkey import HotkeyManager

        assert HotkeyManager().is_listening is False

    def test_dead_listener_is_not_listening(self):
        from unittest.mock import MagicMock

        from rewrite.hotkey import HotkeyManager

        manager = HotkeyManager()
        manager._listener = MagicMock(is_alive=MagicMock(return_value=False))
        assert manager.is_listening is False


@mac_only
def test_mac_listener_uses_active_tap():
    # An intercepting tap needs only Accessibility; pynput's default
    # listen-only tap also needs Input Monitoring.
    from rewrite.hotkey import listener_options

    intercept = listener_options()["darwin_intercept"]
    event = object()
    assert intercept(10, event) is event
