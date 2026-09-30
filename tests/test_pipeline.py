from unittest.mock import MagicMock, patch

import pytest

from rewrite.pipeline import run_rewrite


@pytest.fixture
def clipboard():
    """Mock every clipboard/keystroke call the pipeline makes."""
    with (
        patch("rewrite.pipeline.save_clipboard", return_value="orig") as save,
        patch("rewrite.pipeline.capture_selection") as capture,
        patch("rewrite.pipeline.replace_selection") as replace,
        patch("rewrite.pipeline.restore_clipboard") as restore,
    ):
        yield MagicMock(save=save, capture=capture, replace=replace, restore=restore)


def _provider(result: str) -> MagicMock:
    provider = MagicMock()
    provider.rewrite.return_value = result
    return provider


def test_replaces_corrected_text(clipboard):
    clipboard.capture.return_value = "helo world"
    statuses: list[str] = []

    run_rewrite(lambda: _provider("Hello world."), statuses.append)

    clipboard.replace.assert_called_once_with("Hello world.")
    clipboard.restore.assert_called_once_with("orig")
    assert statuses == ["Capturing…", "Rewriting…", "Done!"]


def test_no_selection_skips_provider(clipboard):
    clipboard.capture.return_value = None
    factory = MagicMock()
    statuses: list[str] = []

    run_rewrite(factory, statuses.append)

    factory.assert_not_called()
    clipboard.replace.assert_not_called()
    clipboard.restore.assert_called_once_with("orig")
    assert statuses[-1] == "Ready"


def test_unchanged_text_is_not_pasted(clipboard):
    clipboard.capture.return_value = "Fine."
    statuses: list[str] = []

    run_rewrite(lambda: _provider("Fine."), statuses.append)

    clipboard.replace.assert_not_called()
    assert statuses[-1] == "Ready"


def test_provider_error_restores_clipboard(clipboard):
    clipboard.capture.return_value = "text"
    statuses: list[str] = []

    def _broken():
        raise ValueError("Gemini API key not configured")

    run_rewrite(_broken, statuses.append)

    clipboard.replace.assert_not_called()
    clipboard.restore.assert_called_once_with("orig")
    assert statuses[-1] == "Error"
