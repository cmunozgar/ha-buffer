"""Generate Home Assistant brand images from official source artwork.

    pip install pillow cairosvg
    python scripts/make_brand.py --icon mark.svg --logo wordmark.svg \
        [--dark-icon mark-white.svg] [--dark-logo wordmark-white.svg]

Sources can be SVG or PNG (transparent background). Writes to
custom_components/buffer/brand/ following the home-assistant/brands spec:
  icon  = square, 256x256 (+ @2x 512x512)
  logo  = landscape, shortest side 128px (+ @2x 256px)
All images are trimmed to their content and saved as optimized PNG.
"""

from __future__ import annotations

import argparse
import io
import pathlib

from PIL import Image

OUT = pathlib.Path(__file__).resolve().parents[1] / "custom_components" / "buffer" / "brand"


def load(path: str, render_px: int = 2048) -> Image.Image:
    p = pathlib.Path(path)
    if p.suffix.lower() == ".svg":
        import cairosvg

        png = cairosvg.svg2png(url=str(p), output_width=render_px)
        img = Image.open(io.BytesIO(png))
    else:
        img = Image.open(p)
    img = img.convert("RGBA")
    bbox = img.getchannel("A").getbbox()
    return img.crop(bbox) if bbox else img


def square(img: Image.Image, size: int) -> Image.Image:
    img = img.copy()
    img.thumbnail((size, size), Image.LANCZOS)
    canvas = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    canvas.paste(img, ((size - img.width) // 2, (size - img.height) // 2), img)
    return canvas


def landscape(img: Image.Image, short_side: int) -> Image.Image:
    scale = short_side / min(img.size)
    return img.resize((round(img.width * scale), round(img.height * scale)), Image.LANCZOS)


def save(img: Image.Image, name: str) -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    img.save(OUT / name, optimize=True)
    print(f"  {name:<20} {img.width}x{img.height}")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--icon", required=True)
    ap.add_argument("--logo")
    ap.add_argument("--dark-icon")
    ap.add_argument("--dark-logo")
    a = ap.parse_args()

    print(f"Writing to {OUT}")
    for prefix, icon_src, logo_src in (
        ("", a.icon, a.logo),
        ("dark_", a.dark_icon, a.dark_logo),
    ):
        if icon_src:
            icon = load(icon_src)
            save(square(icon, 256), f"{prefix}icon.png")
            save(square(icon, 512), f"{prefix}icon@2x.png")
        if logo_src:
            logo = load(logo_src)
            save(landscape(logo, 128), f"{prefix}logo.png")
            save(landscape(logo, 256), f"{prefix}logo@2x.png")


if __name__ == "__main__":
    main()
