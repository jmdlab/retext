<p align="center">
  <img src="assets/icon.png?v=2" alt="Retext" width="128" height="128">
</p>

<h1 align="center">Retext</h1>

<p align="center">
  Select text anywhere in Windows. Press a hotkey. Get it corrected in place.<br>
  Grammar, spelling, punctuation, capitalization — fixed in ~1 second, in the cloud or fully offline.
</p>

<p align="center">
  <img src="https://img.shields.io/badge/platform-Windows%2011-blue" alt="Platform">
  <img src="https://img.shields.io/badge/python-3.12%2B-green" alt="Python">
  <img src="https://img.shields.io/badge/license-MIT-gray" alt="License">
</p>

---

## How it works

```
Select text → Ctrl+Alt+R → text corrected in place
```

Retext sits in your system tray. When you trigger the hotkey, it:

1. Copies the selected text via `Ctrl+C`
2. Sends it to the correction engine — Gemini (cloud) or Ollama (local)
3. Pastes the corrected version via `Ctrl+V`
4. Restores your original clipboard

The language is auto-detected. Slang, tone and words from other languages are kept as written.

## Quick start

1. **Download** `Retext.exe` from [Releases](../../releases)
2. **Run** `Retext.exe` — it appears in the system tray
3. **Right-click** the tray icon → **Settings** → pick an engine:
   - **Gemini** — paste a free API key from [aistudio.google.com/apikey](https://aistudio.google.com/apikey)
   - **Ollama (local)** — install [Ollama](https://ollama.com); Retext starts it and downloads the model for you
4. **Save**, then select text anywhere → press `Ctrl+Alt+R`

## Engines

| | Gemini | Ollama (local) |
|---|---|---|
| Setup | Free API key | [Ollama](https://ollama.com) installed |
| Privacy | Text sent to Google | Never leaves your PC |
| Speed | ~1 s | ~0.1 s on a recent GPU (after the model is loaded) |
| Availability | Can fail with `503 UNAVAILABLE` at peak times | Always on |

With Ollama, Retext launches `ollama serve` if it isn't running, downloads the selected model if it's missing, and preloads it so the first correction is instant. The default model is `gemma4:e4b` — small, fast, and the best of the small models we tested at keeping casual French intact.

## Settings

Right-click the tray icon → **Settings**:

| Setting | Default | Description |
|---------|---------|-------------|
| Engine | Gemini | Gemini (cloud) or Ollama (local) |
| Gemini API key | — | Stored in Windows Credential Manager |
| Gemini model | `gemini-2.5-flash` | Any Gemini model name |
| Ollama model | `gemma4:e4b` | Any installed Ollama model; others download on Save |
| Keep model updated | On | Re-pulls the Ollama model daily so you get upstream fixes |
| Shortcut | `Ctrl+Alt+R` | Click **Change** and press a new combination |
| Launch at Windows startup | Off | Retext waits in the system tray |

Config is stored in `%APPDATA%\Retext\config.json`.

## Build from source

Requires Python 3.12+.

```bash
# Clone
git clone https://github.com/jmdlab/retext.git
cd retext

# Install dependencies
python -m venv .venv
.venv\Scripts\activate
pip install -e .

# Run
python -m rewrite.main

# Build .exe
pip install pyinstaller
pyinstaller --onefile --windowed --name Retext --icon assets\icon.ico --add-data "assets;assets" src\rewrite\main.py
# Output: dist\Retext.exe
```

## Run tests

```bash
pip install pytest ruff
pytest
ruff check src/ tests/
```

## How it's built

| Component | Library |
|-----------|---------|
| Global hotkey | [pynput](https://github.com/moses-palmer/pynput) |
| Clipboard | Win32 `SendInput` + [pyperclip](https://github.com/asweigart/pyperclip) |
| AI (cloud) | [google-genai](https://github.com/googleapis/python-genai) (Gemini) |
| AI (local) | [Ollama](https://ollama.com) HTTP API (stdlib, no extra dependency) |
| System tray | [pystray](https://github.com/moses-palmer/pystray) + [Pillow](https://python-pillow.org/) |
| Settings UI | tkinter (stdlib), DPI-aware, Windows 11 styling |
| Packaging | [PyInstaller](https://pyinstaller.org/) |

## Credits

Icon by [Sergei Kokota](https://www.intuit.ru/the-author/kokovyi-sergej-nikolaevich)

## License

[MIT](LICENSE)
