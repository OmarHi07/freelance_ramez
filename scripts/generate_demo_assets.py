"""Generate the original, legally safe placeholder artwork used by ``seed_demo``.

The images are simple abstract illustrations drawn with Pillow (no photos, no
third-party artwork). Run from the repository root:

    python scripts/generate_demo_assets.py
"""

from __future__ import annotations

import math
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter

OUT = Path(__file__).resolve().parent.parent / "catalog" / "demo_assets"
SIZE = 900
S = 3  # supersampling factor for smooth edges


def hex_rgb(value: str) -> tuple[int, int, int]:
    value = value.lstrip("#")
    return tuple(int(value[i : i + 2], 16) for i in (0, 2, 4))


def mix(a, b, t):
    return tuple(int(a[i] + (b[i] - a[i]) * t) for i in range(3))


def background(primary: str, secondary: str, variant: int) -> Image.Image:
    p, s = hex_rgb(primary), hex_rgb(secondary)
    light = mix(p, (255, 255, 255), 0.55)
    img = Image.new("RGB", (SIZE * S, SIZE * S), light)
    draw = ImageDraw.Draw(img)
    for y in range(0, SIZE * S, 6):
        t = y / (SIZE * S)
        draw.rectangle((0, y, SIZE * S, y + 6), fill=mix(light, p, 0.35 * t))
    # Soft light spots: solid colour layers pasted through blurred masks (no dark halos).
    cx, cy = (0.7 if variant % 2 else 0.3) * SIZE * S, 0.3 * SIZE * S
    spots = [
        ((cx - 900, cy - 900, cx + 900, cy + 900), (255, 255, 255), 110),
        ((0.12 * SIZE * S, 0.70 * SIZE * S, 0.48 * SIZE * S, 1.06 * SIZE * S), mix(s, p, 0.55), 55),
    ]
    for box, color, alpha in spots:
        mask = Image.new("L", img.size, 0)
        ImageDraw.Draw(mask).ellipse(box, fill=alpha)
        mask = mask.filter(ImageFilter.GaussianBlur(140))
        img.paste(Image.new("RGB", img.size, color), (0, 0), mask)
    return img


def pearl(draw, cx, cy, r, color):
    shade = mix(color, (0, 0, 0), 0.12)
    draw.ellipse((cx - r, cy - r, cx + r, cy + r), fill=shade)
    draw.ellipse((cx - r * 0.92, cy - r * 0.95, cx + r * 0.85, cy + r * 0.8), fill=color)
    draw.ellipse((cx - r * 0.5, cy - r * 0.6, cx - r * 0.1, cy - r * 0.25), fill=(255, 255, 255))


def draw_motif(img: Image.Image, motif: str, accent: str, metal: str):
    d = ImageDraw.Draw(img)
    a, m = hex_rgb(accent), hex_rgb(metal)
    W = SIZE * S
    c = W / 2
    lw = 9 * S
    if motif == "earrings":
        for dx in (-150, 150):
            x = c + dx * S
            d.ellipse((x - 26 * S, 250 * S, x + 26 * S, 302 * S), outline=m, width=lw)
            d.line((x, 302 * S, x, 440 * S), fill=m, width=lw // 2)
            pearl(d, x, 520 * S, 80 * S, a)
    elif motif == "necklace":
        d.arc((c - 300 * S, 120 * S, c + 300 * S, 700 * S), 20, 160, fill=m, width=lw // 2)
        for i in range(9):
            ang = math.radians(35 + i * 13.75)
            x = c + 300 * S * math.cos(ang)
            y = 410 * S + 290 * S * math.sin(ang)
            pearl(d, x, y, 22 * S, a)
        pearl(d, c, 740 * S, 60 * S, a)
    elif motif == "bracelet":
        for i in range(18):
            ang = math.radians(i * 20)
            pearl(d, c + 230 * S * math.cos(ang), c + 150 * S * math.sin(ang), 34 * S, a if i % 3 else m)
    elif motif == "ring":
        d.ellipse((c - 190 * S, c - 110 * S, c + 190 * S, c + 270 * S), outline=m, width=lw * 3)
        d.polygon([(c, c - 250 * S), (c + 90 * S, c - 150 * S), (c, c - 60 * S), (c - 90 * S, c - 150 * S)], fill=a)
        d.polygon([(c, c - 250 * S), (c + 40 * S, c - 150 * S), (c, c - 60 * S)], fill=mix(a, (255, 255, 255), 0.35))
    elif motif == "bow":
        d.polygon([(c, c), (c - 300 * S, c - 170 * S), (c - 260 * S, c + 170 * S)], fill=a)
        d.polygon([(c, c), (c + 300 * S, c - 170 * S), (c + 260 * S, c + 170 * S)], fill=a)
        d.polygon(
            [(c - 30 * S, c + 20 * S), (c - 140 * S, c + 330 * S), (c - 60 * S, c + 320 * S)],
            fill=mix(a, (0, 0, 0), 0.1),
        )
        d.polygon(
            [(c + 30 * S, c + 20 * S), (c + 140 * S, c + 330 * S), (c + 60 * S, c + 320 * S)],
            fill=mix(a, (0, 0, 0), 0.1),
        )
        d.rounded_rectangle(
            (c - 60 * S, c - 70 * S, c + 60 * S, c + 70 * S), radius=30 * S, fill=mix(a, (0, 0, 0), 0.18)
        )
    elif motif == "scrunchie":
        for i in range(24):
            ang = math.radians(i * 15)
            r = 230 * S + (20 * S if i % 2 else -10 * S)
            x, y = c + r * math.cos(ang), c + r * math.sin(ang)
            d.ellipse((x - 85 * S, y - 85 * S, x + 85 * S, y + 85 * S), fill=mix(a, (255, 255, 255), 0.15 * (i % 2)))
        d.ellipse((c - 150 * S, c - 150 * S, c + 150 * S, c + 150 * S), fill=mix(a, (255, 255, 255), 0.55))
    elif motif == "clip":
        for j, dy in enumerate((-160, 0, 160)):
            y = c + dy * S
            d.rounded_rectangle((c - 280 * S, y - 34 * S, c + 280 * S, y + 34 * S), radius=34 * S, fill=m)
            for k in range(4):
                pearl(d, c - 180 * S + k * 120 * S, y, 30 * S, a if (j + k) % 2 else mix(a, (255, 255, 255), 0.4))
    elif motif == "moon":
        bg = img.getpixel((int(c + 330 * S), int(c - 330 * S)))
        d.ellipse((c - 250 * S, c - 250 * S, c + 250 * S, c + 250 * S), fill=m)
        d.ellipse((c - 110 * S, c - 330 * S, c + 330 * S, c + 110 * S), fill=bg)
        for x, y, r in ((c + 180, c + 170, 30), (c + 250, c - 10, 18), (c - 40, c - 300, 22)):
            d.regular_polygon((x * 1.0, y * 1.0, r * S), 4, rotation=45, fill=a)
    elif motif == "daisy":
        for i in range(10):
            ang = math.radians(i * 36)
            x, y = c + 170 * S * math.cos(ang), c + 170 * S * math.sin(ang)
            d.ellipse((x - 95 * S, y - 95 * S, x + 95 * S, y + 95 * S), fill=(255, 255, 255))
        d.ellipse((c - 110 * S, c - 110 * S, c + 110 * S, c + 110 * S), fill=a)
    elif motif == "heart":
        r = 150 * S
        d.ellipse((c - 2 * r + 20 * S, c - 1.3 * r, c + 20 * S, c + 0.7 * r), fill=a)
        d.ellipse((c - 20 * S, c - 1.3 * r, c + 2 * r - 20 * S, c + 0.7 * r), fill=a)
        d.polygon([(c - 1.93 * r, c), (c + 1.93 * r, c), (c, c + 2.2 * r)], fill=a)


def make(name: str, primary: str, secondary: str, motif: str, accent: str, metal: str, variant: int = 0):
    img = background(primary, secondary, variant)
    draw_motif(img, motif, accent, metal)
    img = img.resize((SIZE, SIZE), Image.Resampling.LANCZOS)
    img.save(OUT / f"{name}.webp", "WEBP", quality=80, method=6)


def make_logo(name: str, primary: str, secondary: str, letter_motif: str):
    size = 480 * S
    img = Image.new("RGB", (size, size), hex_rgb(primary))
    d = ImageDraw.Draw(img)
    s = hex_rgb(secondary)
    d.ellipse((size * 0.12, size * 0.12, size * 0.88, size * 0.88), outline=s, width=14 * S)
    c = size / 2
    if letter_motif == "pearl":
        pearl(d, c, c, 110 * S, (255, 255, 255))
    elif letter_motif == "rose":
        for i in range(6):
            ang = math.radians(i * 60)
            x, y = c + 70 * S * math.cos(ang), c + 70 * S * math.sin(ang)
            d.ellipse((x - 70 * S, y - 70 * S, x + 70 * S, y + 70 * S), fill=mix(s, (255, 255, 255), 0.35))
        d.ellipse((c - 55 * S, c - 55 * S, c + 55 * S, c + 55 * S), fill=s)
    elif letter_motif == "moon":
        d.ellipse((c - 120 * S, c - 120 * S, c + 120 * S, c + 120 * S), fill=s)
        d.ellipse((c - 60 * S, c - 160 * S, c + 160 * S, c + 60 * S), fill=hex_rgb(primary))
    elif letter_motif == "bow":
        d.polygon([(c, c), (c - 150 * S, c - 90 * S), (c - 130 * S, c + 90 * S)], fill=s)
        d.polygon([(c, c), (c + 150 * S, c - 90 * S), (c + 130 * S, c + 90 * S)], fill=s)
        d.ellipse((c - 35 * S, c - 35 * S, c + 35 * S, c + 35 * S), fill=mix(s, (0, 0, 0), 0.2))
    img = img.resize((480, 480), Image.Resampling.LANCZOS)
    img.save(OUT / f"{name}.webp", "WEBP", quality=85, method=6)


BRANDS = {
    "lulu-pearl": ("#F8C8DC", "#9E526F", "pearl"),
    "rose-atelier": ("#F6DCCB", "#8C4B3E", "rose"),
    "luna-charm": ("#DCD3F5", "#5B4A9E", "moon"),
    "mint-bow": ("#CDEBDF", "#2F6B55", "bow"),
}

PRODUCTS = [
    ("pearl-drop-earrings", "lulu-pearl", "earrings", "#FFFDF8", "#C9A85C"),
    ("pearl-hair-clip-set", "lulu-pearl", "clip", "#FFFFFF", "#D6B46A"),
    ("mini-pearl-necklace", "lulu-pearl", "necklace", "#FFFDF8", "#C9A85C"),
    ("satin-scrunchie-trio", "rose-atelier", "scrunchie", "#E8A7A0", "#B88A6A"),
    ("rose-charm-bracelet", "rose-atelier", "bracelet", "#E7A1A8", "#C9A85C"),
    ("heart-stud-earrings", "rose-atelier", "heart", "#D9757F", "#C9A85C"),
    ("crescent-moon-necklace", "luna-charm", "moon", "#FFFFFF", "#C9A85C"),
    ("star-stacking-rings", "luna-charm", "ring", "#8E7CD6", "#C9A85C"),
    ("lavender-bead-bracelet", "luna-charm", "bracelet", "#B6A6EA", "#FFFFFF"),
    ("velvet-bow-barrette", "mint-bow", "bow", "#3F8C70", "#C9A85C"),
    ("daisy-hoop-earrings", "mint-bow", "daisy", "#F3C969", "#C9A85C"),
    ("enamel-flower-ring", "mint-bow", "ring", "#F29BB0", "#C9A85C"),
]


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    for slug, (primary, secondary, motif) in BRANDS.items():
        make_logo(f"brand-{slug}", primary, secondary, motif)
    for slug, brand, motif, accent, metal in PRODUCTS:
        primary, secondary, _ = BRANDS[brand]
        make(f"{slug}-1", primary, secondary, motif, accent, metal, 0)
        make(f"{slug}-2", primary, secondary, motif, metal if motif != "bow" else accent, accent, 1)
    print(f"Wrote {len(list(OUT.glob('*.webp')))} files to {OUT}")


if __name__ == "__main__":
    main()
