import io
import json
import urllib.error
from unittest.mock import MagicMock, patch

import pytest

from rewrite.model_updater import ModelUpdater
from rewrite.providers import ollama
from rewrite.providers.base import BaseProvider
from rewrite.providers.ollama import OllamaError, OllamaProvider
from rewrite.rewriter import get_provider


def _fake_urlopen(responses: dict[str, dict]):
    """Return a urlopen stand-in that answers by URL path and records calls."""
    calls: list[tuple[str, dict | None]] = []

    def _open(req, timeout=None):
        path = req.full_url.split("11434", 1)[1]
        body = json.loads(req.data) if req.data else None
        calls.append((path, body))
        resp = MagicMock()
        resp.__enter__.return_value = io.BytesIO(
            json.dumps(responses.get(path, {})).encode(),
        )
        return resp

    return _open, calls


class TestOllamaProvider:
    def test_is_provider(self):
        assert isinstance(OllamaProvider(), BaseProvider)

    def test_empty_model_raises(self):
        with pytest.raises(ValueError, match="Ollama model"):
            OllamaProvider(model="")

    def test_rewrite_sends_chat_without_thinking(self):
        opener, calls = _fake_urlopen(
            {"/api/chat": {"message": {"content": "Bonjour."}}},
        )
        with patch("urllib.request.urlopen", opener):
            out = OllamaProvider(model="m").rewrite("bonjour", "SYS")
        assert out == "Bonjour."
        assert calls[0][0] == "/api/version"  # liveness check first
        path, body = calls[1]
        assert path == "/api/chat"
        assert body["model"] == "m"
        assert body["think"] is False
        assert body["stream"] is False
        assert body["messages"][0] == {"role": "system", "content": "SYS"}
        assert body["messages"][1] == {"role": "user", "content": "bonjour"}

    def test_empty_response_returns_input(self):
        opener, _ = _fake_urlopen({"/api/chat": {"message": {"content": ""}}})
        with patch("urllib.request.urlopen", opener):
            assert OllamaProvider(model="m").rewrite("abc") == "abc"

    def test_server_down_and_not_installed_raises_clear_error(self):
        err = urllib.error.URLError("refused")
        with (
            patch("urllib.request.urlopen", side_effect=err),
            patch.object(ollama, "_find_executable", return_value=None),
            pytest.raises(OllamaError, match="not installed"),
        ):
            OllamaProvider(model="m").rewrite("x")

    def test_server_down_gets_started(self):
        state = {"up": False}

        def _open(req, timeout=None):
            if not state["up"]:
                raise urllib.error.URLError("refused")
            resp = MagicMock()
            resp.__enter__.return_value = io.BytesIO(b"{}")
            return resp

        def _popen(args, **kwargs):
            assert args == ["C:/ollama.exe", "serve"]
            state["up"] = True

        with (
            patch("urllib.request.urlopen", _open),
            patch.object(ollama, "_find_executable", return_value="C:/ollama.exe"),
            patch.object(ollama.subprocess, "Popen", side_effect=_popen) as popen,
        ):
            ollama.ensure_running()
        popen.assert_called_once()

    def test_running_server_is_not_restarted(self):
        opener, _ = _fake_urlopen({"/api/version": {"version": "x"}})
        with (
            patch("urllib.request.urlopen", opener),
            patch.object(ollama.subprocess, "Popen") as popen,
        ):
            ollama.ensure_running()
        popen.assert_not_called()

    def test_list_models_sorted(self):
        opener, _ = _fake_urlopen(
            {"/api/tags": {"models": [{"name": "b:1"}, {"name": "a:1"}]}},
        )
        with patch("urllib.request.urlopen", opener):
            assert ollama.list_models() == ["a:1", "b:1"]


class TestGetProviderSwitch:
    def test_ollama_selected(self):
        provider = get_provider({"provider": "ollama", "ollama_model": "m"})
        assert isinstance(provider, OllamaProvider)
        assert provider.model == "m"

    def test_ollama_needs_no_api_key(self):
        provider = get_provider(
            {"provider": "ollama", "ollama_model": "m", "gemini_api_key": ""},
        )
        assert isinstance(provider, OllamaProvider)

    def test_unknown_provider_raises(self):
        with pytest.raises(ValueError, match="Unknown provider"):
            get_provider({"provider": "nope"})


class TestModelUpdater:
    def _run(self, installed: list[str], auto_update: bool):
        reports: list[str] = []
        opener, calls = _fake_urlopen({
            "/api/tags": {"models": [{"name": n} for n in installed]},
            "/api/pull": {"status": "success"},
        })
        with patch("urllib.request.urlopen", opener):
            ModelUpdater(
                "m:1", ollama.DEFAULT_URL, auto_update, reports.append,
            ).run_once()
        return [path for path, _ in calls if path != "/api/version"], reports

    def test_missing_model_is_downloaded_even_without_auto_update(self):
        paths, reports = self._run([], auto_update=False)
        assert paths == ["/api/tags", "/api/pull", "/api/generate"]
        assert any("Downloading" in r for r in reports)

    def test_installed_model_updated_when_auto_update(self):
        paths, _ = self._run(["m:1"], auto_update=True)
        assert paths == ["/api/tags", "/api/pull", "/api/generate"]

    def test_installed_model_not_pulled_when_auto_update_off(self):
        paths, _ = self._run(["m:1"], auto_update=False)
        assert paths == ["/api/tags", "/api/generate"]

    def test_failure_is_reported_not_raised(self):
        reports: list[str] = []
        err = urllib.error.URLError("refused")
        with (
            patch("urllib.request.urlopen", side_effect=err),
            patch.object(ollama, "_find_executable", return_value=None),
        ):
            ModelUpdater("m", ollama.DEFAULT_URL, True, reports.append).run_once()
        assert reports and "not installed" in reports[-1]
