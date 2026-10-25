#!/usr/bin/env python3
"""Generate icon-512.png — brand §6: eclipse motif on navy
(#0d1b2a), one per-product glyph. Forecast's glyph is a priced
curve: a line of venue prices rising over time with its depth
shaded beneath, inside the gradient eclipse ring. PIL only;
deterministic."""
from PIL import Image, ImageDraw

S = 512
NAVY = (13, 27, 42, 255)
STOPS = [(15, 246, 247), (0, 212, 255), (123, 44, 191)]


def lerp(a, b, t):
    return tuple(int(a[i] + (b[i] - a[i]) * t) for i in range(3)) + (255,)


def grad(t):
    return lerp(STOPS[0], STOPS[1], t * 2) if t < 0.5 else \
        lerp(STOPS[1], STOPS[2], (t - 0.5) * 2)


def main():
    img = Image.new("RGBA", (S, S), NAVY)
    d = ImageDraw.Draw(img)
    ring = [54, 54, 458, 458]
    for i in range(72):
        t = i / 72
        d.arc(ring, start=i * 5, end=i * 5 + 6, fill=grad(t), width=13)
    d.ellipse([126, 126, 386, 386], fill=NAVY)
    pts = [(158, 336), (206, 310), (248, 322), (292, 262),
           (330, 238), (356, 186)]
    # Depth shading beneath the curve.
    d.polygon(pts + [(356, 356), (158, 356)], fill=(0, 212, 255, 70))
    for a, b in zip(pts, pts[1:]):
        d.line([a, b], fill=grad(0.3), width=8)
    for x, y in pts:
        d.ellipse([x - 8, y - 8, x + 8, y + 8], fill=grad(0.55))
    # Axis.
    d.line([(150, 356), (364, 356)], fill=(160, 174, 192, 255), width=4)
    img.save("icon-512.png")
    print("wrote icon-512.png", img.size, img.mode)


if __name__ == "__main__":
    main()
