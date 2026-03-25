<p align="center">
  <img src="assets/icon.png?v=2" alt="Retext" width="128" height="128">
</p>

<h1 align="center">Retext</h1>

<p align="center">
  Select text anywhere in Windows. Press a hotkey. Get it corrected in place.<br>
  Grammar, spelling, punctuation, capitalization — fixed in ~1 second.
</p>

<p align="center">
  <img src="https://img.shields.io/badge/platform-Windows%2011-blue" alt="Platform">
  <img src="https://img.shields.io/badge/python-3.12%2B-green" alt="Python">
  <img src="https://img.shields.io/badge/license-MIT-gray" alt="License">
</p>

---

## How it works

```
Select text → Ctrl+Shift+R → text corrected in place
```

Retext sits in your system tray. When you trigger the hotkey, it:

1. Copies the selected text via `Ctrl+C`
2. Sends it to the Gemini API for correction
3. Pastes the corrected version via `Ctrl+V`
4. Restores your original clipboard

The language is auto-detected — works with any language Gemini supports.

## Quick start

1. **Download** `Retext.exe` from [Releases](../../releases)
2. **Get a free API key** at [aistudio.google.com/apikey](https://aistudio.google.com/apikey)
3. **Run** `Retext.exe` — it appears in the system tray
4. **Right-click** the tray icon → **Settings** → paste your API key → **Save**
5. **Select text** anywhere → press `Ctrl+Shift+R`

## Settings

Right-click the tray icon → **Settings**:

| Setting | Default | Description |
|---------|---------|-------------|
| API Key | — | Your Gemini API key ([get one free](https://aistudio.google.com/apikey)) |
| Model | `gemini-2.5-flash` | Any Gemini model name |
| Hotkey | `Ctrl+Shift+R` | Click **Record** to change |

Config is stored in `%APPDATA%\Retext\config.json`. The API key is stored securely in Windows Credential Manager.

## Build from source

Requires Python 3.12+.

```bash
# Clone
git clone https://github.com/probablyagoodusername/Retext.git
cd Retext

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
ruff check src/
```

## How it's built

| Component | Library |
|-----------|---------|
| Global hotkey | [pynput](https://github.com/moses-palmer/pynput) |
| Clipboard | [pyperclip](https://github.com/asweigart/pyperclip) + pynput |
| AI | [google-genai](https://github.com/googleapis/python-genai) (Gemini) |
| System tray | [pystray](https://github.com/moses-palmer/pystray) + [Pillow](https://python-pillow.org/) |
| Settings UI | tkinter (stdlib) |
| Packaging | [PyInstaller](https://pyinstaller.org/) |

## Credits

Icon by [Sergei Kokota](https://www.intuit.ru/the-author/kokovyi-sergej-nikolaevich)

## License

[MIT](LICENSE)
