"""
Draw the Kestrova app icon (assets/icon.png, 1024 x 1024): a biconvex lens
bringing three parallel rays to a focus. electron-builder derives the
Windows .ico and macOS .icns from this PNG.

    pip install pillow numpy && python tools/make_icon.py
"""

import math
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw

N = 1024
S = 4  # supersampling
W = N * S

NAVY = (15, 23, 42, 255)
AMBER = (251, 191, 36, 255)
GLASS = (125, 211, 252, 220)
FOCUS = (254, 243, 199, 255)


def disk(cx: float, cy: float, r: float) -> np.ndarray:
    mask = Image.new("L", (W, W), 0)
    ImageDraw.Draw(mask).ellipse((cx - r, cy - r, cx + r, cy + r), fill=255)
    return np.array(mask)


def main() -> None:
    img = Image.new("RGBA", (W, W), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    m = int(0.09 * W)  # margin, as macOS icons have
    d.rounded_rectangle((m, m, W - m, W - m), radius=int(0.2 * W), fill=NAVY)

    cx, cy = 0.40 * W, 0.50 * W
    focus = (0.80 * W, cy)
    half_h = 0.27 * W  # lens semi-aperture
    R = 0.62 * W  # radius of both surfaces
    sag = R - math.sqrt(R * R - half_h * half_h)

    width = int(0.022 * W)
    for h in (-0.17 * W, 0.0, 0.17 * W):
        y = cy + h
        d.line((0.16 * W, y, cx, y), fill=AMBER, width=width)
        d.line((cx, y, *focus), fill=AMBER, width=width)

    # biconvex lens: the intersection of the two surface circles
    lens = np.minimum(disk(cx - sag + R, cy, R), disk(cx + sag - R, cy, R))
    glass = Image.new("RGBA", (W, W), GLASS)
    img.alpha_composite(
        Image.composite(glass, Image.new("RGBA", (W, W)), Image.fromarray(lens))
    )

    r = 0.03 * W
    ImageDraw.Draw(img).ellipse(
        (focus[0] - r, focus[1] - r, focus[0] + r, focus[1] + r), fill=FOCUS
    )
    out = Path(__file__).resolve().parents[1] / "assets" / "icon.png"
    img.resize((N, N), Image.LANCZOS).save(out)
    print(out)


if __name__ == "__main__":
    main()
