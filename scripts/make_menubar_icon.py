"""Generate assets/menubar.png — the macOS menu bar template icon.

Keeps only the dark outline strokes of icon.png as a black+alpha image,
so macOS can tint it for light/dark menu bars. Run once after changing
icon.png: python scripts/make_menubar_icon.py
"""

from pathlib import Path

from PIL import Image, ImageFilter

ROOT = Path(__file__).resolve().parent.parent
SIZE = 44  # 22pt @2x — rumps draws it at 20x20pt

src = Image.open(ROOT / "assets" / "icon.png").convert("RGBA")
gray = src.convert("L")
alpha = src.getchannel("A")

# Stroke pixels: opaque and dark. Everything else becomes transparent.
mask = Image.eval(gray, lambda v: 255 if v < 128 else 0)
mask = Image.composite(mask, Image.new("L", src.size, 0), alpha)
# Thicken strokes so they survive the 512 → 44 px downscale.
mask = mask.filter(ImageFilter.MaxFilter(15))
mask = mask.resize((SIZE, SIZE), Image.LANCZOS)

out = Image.new("RGBA", (SIZE, SIZE), (0, 0, 0, 0))
out.putalpha(mask)
out.save(ROOT / "assets" / "menubar.png")
print("wrote assets/menubar.png")
