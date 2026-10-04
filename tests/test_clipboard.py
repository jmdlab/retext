from unittest.mock import patch

from rewrite import clipboard


class _ObjCString(str):
    """Stands in for objc.pyobjc_unicode, which pyperclip returns on macOS."""


def test_save_clipboard_returns_plain_str():
    with patch("rewrite.clipboard.pyperclip.paste", return_value=_ObjCString("hi")):
        result = clipboard.save_clipboard()
    assert type(result) is str
    assert result == "hi"


def test_paste_text_returns_plain_str():
    # google-genai silently serializes str subclasses as empty content
    with patch("rewrite.clipboard.pyperclip.paste", return_value=_ObjCString("hi")):
        result = clipboard._paste_text()
    assert type(result) is str
