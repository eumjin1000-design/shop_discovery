"""Generate the Shop Discovery app icon (icon.ico) on the desktop.

Style: blue rounded-square background, a white shopping bag, and a white
magnifying glass overlapping its upper-right corner. Drawn at 4x then
downsampled for clean edges, and saved as a multi-resolution .ico.

Run:
    python make_icon.py
"""
from __future__ import annotations

import os

from PIL import Image, ImageDraw

SCALE = 4
S = 256 * SCALE                      # working canvas size
BLUE = (25, 103, 210, 255)           # background top
BLUE_DARK = (10, 64, 150, 255)       # background bottom (gradient)
GLASS = (66, 133, 244, 255)          # lens interior tint
WHITE = (255, 255, 255, 255)


def _rounded_bg() -> Image.Image:
    img = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    for y in range(S):                       # vertical blue gradient
        t = y / S
        d.line(
            [(0, y), (S, y)],
            fill=(
                int(BLUE[0] * (1 - t) + BLUE_DARK[0] * t),
                int(BLUE[1] * (1 - t) + BLUE_DARK[1] * t),
                int(BLUE[2] * (1 - t) + BLUE_DARK[2] * t),
                255,
            ),
        )
    mask = Image.new("L", (S, S), 0)
    ImageDraw.Draw(mask).rounded_rectangle(
        [0, 0, S - 1, S - 1], radius=int(S * 0.22), fill=255
    )
    img.putalpha(mask)
    return img


def _shopping_bag(d: ImageDraw.ImageDraw) -> None:
    cx, cy = S * 0.45, S * 0.60
    w, h = S * 0.40, S * 0.38
    left, right = cx - w / 2, cx + w / 2
    top, bottom = cy - h / 2, cy + h / 2
    # Handle: an open arc (top half of an ellipse) rising above the bag mouth.
    hw = w * 0.52
    htop = top - h * 0.34
    d.arc(
        [cx - hw / 2, htop, cx + hw / 2, top + h * 0.10],
        start=180, end=360, fill=WHITE, width=int(S * 0.028),
    )
    # Bag body.
    d.rounded_rectangle([left, top, right, bottom], radius=int(S * 0.04), fill=WHITE)
    # Mouth line.
    d.line([left + w * 0.06, top, right - w * 0.06, top],
           fill=BLUE, width=int(S * 0.013))


def _magnifier(d: ImageDraw.ImageDraw) -> None:
    cx, cy = S * 0.66, S * 0.40
    r = S * 0.155
    ring_w = int(S * 0.05)
    # Handle first (so the lens ring sits on top of it).
    hx, hy = cx + r * 0.70, cy + r * 0.70
    ex, ey = hx + S * 0.135, hy + S * 0.135
    d.line([hx, hy, ex, ey], fill=WHITE, width=int(S * 0.062))
    d.ellipse([ex - S * 0.034, ey - S * 0.034, ex + S * 0.034, ey + S * 0.034],
              fill=WHITE)
    # Lens: white ring with a tinted-blue glass interior.
    d.ellipse([cx - r, cy - r, cx + r, cy + r], fill=WHITE)
    ri = r - ring_w
    d.ellipse([cx - ri, cy - ri, cx + ri, cy + ri], fill=GLASS)
    # Tiny highlight on the glass.
    hl = ri * 0.40
    d.ellipse([cx - ri * 0.55 - hl, cy - ri * 0.55 - hl,
               cx - ri * 0.55 + hl, cy - ri * 0.55 + hl], fill=WHITE)


def build() -> Image.Image:
    base = _rounded_bg()
    d = ImageDraw.Draw(base)
    _shopping_bag(d)
    _magnifier(d)
    return base.resize((256, 256), Image.LANCZOS)


def main() -> None:
    img = build()
    desktop = os.path.join(os.path.expanduser("~"), "Desktop")
    if not os.path.isdir(desktop):
        desktop = os.path.expanduser("~")
    out = os.path.join(desktop, "icon.ico")
    img.save(out, format="ICO",
             sizes=[(256, 256), (128, 128), (64, 64), (48, 48), (32, 32), (16, 16)])
    img.save(os.path.join(os.path.dirname(__file__), "icon_preview.png"))
    print(f"Saved: {out}")
    print(f"Preview: {os.path.join(os.path.dirname(__file__), 'icon_preview.png')}")


if __name__ == "__main__":
    main()
