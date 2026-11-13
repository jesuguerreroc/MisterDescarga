"""Genera assets/icon.ico y assets/icon.png a partir de assets/icon-1024.png.

El dibujo original está en assets/logo/pinguino-icon.svg. Si lo cambias, expórtalo
a PNG de 1024x1024 (con Inkscape, un navegador, etc.) como assets/icon-1024.png
y ejecuta:  python scripts/make_icon.py
"""

from pathlib import Path

from PIL import Image

ASSETS = Path(__file__).resolve().parent.parent / "assets"

if __name__ == "__main__":
    img = Image.open(ASSETS / "icon-1024.png").convert("RGBA")
    img.resize((256, 256), Image.LANCZOS).save(ASSETS / "icon.png")
    img.save(ASSETS / "icon.ico", sizes=[(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)])
    print("ok:", ASSETS / "icon.ico")
