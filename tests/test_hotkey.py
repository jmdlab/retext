import pytest

from rewrite.hotkey import _parse_hotkey, _vk_for_key


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
