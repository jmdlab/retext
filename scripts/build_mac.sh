#!/usr/bin/env bash
# Build dist/Retext.app — a menu bar app (no Dock icon), ad-hoc signed.
set -euo pipefail
cd "$(dirname "$0")/.."

PY="${PYTHON:-.venv/bin/python}"
"$PY" -m pip install -q -e . pyinstaller

# App icon: icon.png → Retext.icns
ICONSET=build/Retext.iconset
rm -rf "$ICONSET" && mkdir -p "$ICONSET"
for size in 16 32 128 256 512; do
  sips -z $size $size assets/icon.png --out "$ICONSET/icon_${size}x${size}.png" >/dev/null
  double=$((size * 2))
  sips -z $double $double assets/icon.png --out "$ICONSET/icon_${size}x${size}@2x.png" >/dev/null
done
iconutil -c icns "$ICONSET" -o build/Retext.icns

"$PY" -m PyInstaller --noconfirm --windowed \
  --name Retext \
  --icon build/Retext.icns \
  --osx-bundle-identifier com.jmdlab.retext \
  --add-data "assets:assets" \
  --exclude-module tkinter \
  --exclude-module pystray \
  src/rewrite/main_mac.py

PLIST=dist/Retext.app/Contents/Info.plist
VERSION=$("$PY" -c "import tomllib; print(tomllib.load(open('pyproject.toml','rb'))['project']['version'])")
# Menu bar only — no Dock icon, no app switcher entry.
plutil -replace LSUIElement -bool true "$PLIST"
plutil -replace CFBundleShortVersionString -string "$VERSION" "$PLIST"
plutil -replace NSAppleEventsUsageDescription \
  -string "Retext sends Copy and Paste to the app you're typing in." "$PLIST"

codesign --force --deep --sign - dist/Retext.app

echo
echo "Built dist/Retext.app — move it to /Applications, then open it."
