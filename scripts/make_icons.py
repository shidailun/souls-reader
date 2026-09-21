# -*- coding: utf-8 -*-
"""Home-screen icons for the installed app (iPhone: Add to Home Screen).

The same guitar as the page's favicon, drawn with PIL so there is no SVG
renderer to install. Deliberately not the book cover: icons are served in the
clear, and the cover is the publisher's.

    python scripts/make_icons.py
"""
from pathlib import Path
from PIL import Image, ImageDraw

OUT = Path(__file__).resolve().parents[1] / 'public' / 'icons'
BG, HOT = (11, 11, 13), (232, 80, 58)


def guitar(n):
    s = 4                                    # draw big, shrink: smooth edges
    im = Image.new('RGB', (n * s, n * s), BG)
    d = ImageDraw.Draw(im)
    u = n * s / 64                           # the favicon's 64-unit grid
    P = lambda x, y: (x * u, y * u)
    # neck, from the headstock down to the body, as a thick rotated bar
    d.line([P(43, 9), P(24, 28)], fill=HOT, width=int(6 * u))
    d.polygon([P(40, 6), P(46, 12), P(50, 8), P(44, 2)], fill=HOT)   # headstock
    circle = lambda x, y, r, c: d.ellipse([P(x - r, y - r), P(x + r, y + r)], fill=c)
    circle(31, 33, 8.5, HOT)                                          # upper bout
    circle(22, 42, 12, HOT)                                           # lower bout
    circle(27, 37, 3.6, BG)                                           # sound hole
    d.line([P(15, 45), P(21, 51)], fill=BG, width=int(1.6 * u))       # bridge
    return im.resize((n, n), Image.LANCZOS)


OUT.mkdir(parents=True, exist_ok=True)
for n in (180, 192, 512):
    guitar(n).save(OUT / f'icon-{n}.png')
print('wrote', ', '.join(f'icon-{n}.png' for n in (180, 192, 512)))
