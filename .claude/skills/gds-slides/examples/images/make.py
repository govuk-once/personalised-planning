"""Draw the how-to deck's two illustrations as SVG, then PNG through macOS Quick Look.

    /usr/bin/python3 examples/images/make.py

cover-claude-slides: a deck of slides on navy, with a Claude-style spark and a few sparkles.
notes-to-deck: notes, through a Claude Code terminal, into a slide deck.

Both are sized for the right half of a slide (363 x 405pt), at four times that. The spark is
drawn in the style of Claude's mark, not copied from it: swap in the official logo from the
brand assets for anything that leaves the team. Colours are the template's, plus Claude orange.
"""

import math
import os
import random
import shutil
import subprocess

HERE = os.path.dirname(os.path.abspath(__file__))
W, H = 1452, 1620
NAVY, NAVY2, NAVY3 = "#04084A", "#1B2070", "#323A8E"
CYAN, PAPER, RULE, MUTED = "#16EEEE", "#F8F8F8", "#CBCBCB", "#8A8FA8"
ORANGE, YELLOW = "#D97757", "#FFDD00"


def spark(cx, cy, r, color=ORANGE, rays=12, seed=4):
    """A radial burst of tapered rays of uneven length."""
    rnd = random.Random(seed)
    parts = []
    for k in range(rays):
        a = 2 * math.pi * k / rays + rnd.uniform(-0.12, 0.12)
        length = r * (1.0 if k % 2 == 0 else 0.8) * rnd.uniform(0.92, 1.04)
        base, tip = r * 0.15, r * 0.055
        ux, uy = math.cos(a), math.sin(a)
        px, py = -uy, ux
        pts = [(cx + px * base, cy + py * base), (cx + ux * length + px * tip, cy + uy * length + py * tip),
               (cx + ux * length - px * tip, cy + uy * length - py * tip), (cx - px * base, cy - py * base)]
        parts.append("M" + " L".join(f"{x:.1f},{y:.1f}" for x, y in pts) + " Z")
    return f'<path d="{" ".join(parts)}" fill="{color}" stroke="{color}" stroke-width="{r * 0.07:.1f}" stroke-linejoin="round"/>'


def sparkle(cx, cy, s, color):
    """A four-pointed sparkle with curved sides."""
    return (f'<path d="M{cx},{cy - s} Q{cx},{cy} {cx + s},{cy} Q{cx},{cy} {cx},{cy + s} '
            f'Q{cx},{cy} {cx - s},{cy} Q{cx},{cy} {cx},{cy - s} Z" fill="{color}"/>')


def slide(x, y, w, chart=True, fill=PAPER):
    """An abstract slide: title bar, text lines, a small bar chart and the cyan GDS tag."""
    h = w * 9 / 16
    u = w / 100
    out = [f'<rect x="{x}" y="{y}" width="{w}" height="{h}" fill="{fill}"/>',
           f'<rect x="{x + 7 * u}" y="{y + 9 * u}" width="{46 * u}" height="{5.5 * u}" fill="{NAVY}"/>']
    for k, frac in enumerate((40, 34, 37)):
        out.append(f'<rect x="{x + 7 * u}" y="{y + (22 + 6.5 * k) * u}" width="{frac * u}" height="{2.6 * u}" fill="{RULE}"/>')
    if chart:
        for k, hgt in enumerate((9, 15, 12, 21)):
            out.append(f'<rect x="{x + (60 + 8 * k) * u}" y="{y + (44 - hgt) * u}" width="{5.5 * u}" height="{hgt * u}" '
                       f'fill="{CYAN if k == 3 else NAVY3}"/>')
        out.append(f'<rect x="{x + 58 * u}" y="{y + 44 * u}" width="{34 * u}" height="{0.6 * u}" fill="{NAVY}"/>')
    out.append(f'<rect x="{x + 4 * u}" y="{y + h - 7 * u}" width="{9 * u}" height="{3.2 * u}" fill="{CYAN}"/>')
    return "".join(out)


def cover():
    w = 940
    x, y = (W - w) / 2 + 40, 600
    body = [f'<rect width="{W}" height="{H}" fill="{NAVY}"/>',
            # the deck behind, offset up and to the left
            f'<rect x="{x - 90}" y="{y - 90}" width="{w}" height="{w * 9 / 16}" fill="{NAVY3}"/>',
            f'<rect x="{x - 45}" y="{y - 45}" width="{w}" height="{w * 9 / 16}" fill="{NAVY2}" stroke="{NAVY3}" stroke-width="2"/>',
            slide(x, y, w),
            spark(x + w - 70, y - 10, 125),
            sparkle(x + w - 260, y - 150, 34, CYAN), sparkle(x + w + 60, y + 190, 22, PAPER),
            sparkle(x + w - 150, y - 230, 16, PAPER), sparkle(x - 40, y + w * 9 / 16 + 130, 26, CYAN),
            sparkle(x + 60, y - 230, 14, CYAN)]
    return body


def notes_to_deck():
    rnd = random.Random(7)
    body = [f'<rect width="{W}" height="{H}" fill="#E9EAF2"/>']
    # notes: a lined page and a sticky note, slightly turned, top left
    body.append('<g transform="translate(140 130) rotate(-5)">'
                f'<rect width="500" height="560" fill="#FFFFFF"/>'
                f'<rect width="500" height="52" fill="{NAVY}"/>')
    for k in range(7):
        yy = 120 + 62 * k
        body.append(f'<line x1="40" y1="{yy + 18}" x2="460" y2="{yy + 18}" stroke="#DDDEE8" stroke-width="3"/>')
        end = rnd.uniform(200, 410) if k % 4 != 3 else rnd.uniform(110, 200)
        pts = " ".join(f"{40 + t:.0f},{yy + 6 * math.sin(t / 17 + k):.1f}" for t in range(0, int(end), 12))
        body.append(f'<polyline points="{pts}" fill="none" stroke="{NAVY3}" stroke-width="7" stroke-linecap="round" stroke-linejoin="round"/>')
    body.append('</g>')
    body.append(f'<g transform="translate(500 470) rotate(7)"><rect width="220" height="220" fill="{YELLOW}"/>'
                + "".join(f'<rect x="28" y="{44 + 40 * k}" width="{w}" height="11" rx="5.5" fill="#8A7A00" opacity=".55"/>'
                          for k, w in enumerate((150, 115, 135, 80))) + '</g>')
    # Claude Code: a terminal window with the spark and a prompt, between notes and deck
    tx, ty, tw, th = 790, 740, 500, 300
    body += [f'<path d="M560,760 C560,900 650,960 {tx - 20},{ty + 150}" fill="none" stroke="{NAVY}" stroke-width="7" stroke-dasharray="20 16"/>',
             f'<path d="M{tx - 48},{ty + 128} l30,22 l-28,26" fill="none" stroke="{NAVY}" stroke-width="7" stroke-linecap="round" stroke-linejoin="round"/>',
             f'<rect x="{tx}" y="{ty}" width="{tw}" height="{th}" fill="{NAVY}"/>',
             f'<rect x="{tx}" y="{ty}" width="{tw}" height="44" fill="{NAVY2}"/>']
    for k, c in enumerate(("#F8F8F8", "#9CA0C2", "#6A70A6")):
        body.append(f'<circle cx="{tx + 30 + 30 * k}" cy="{ty + 22}" r="9" fill="{c}"/>')
    body += [spark(tx + 120, ty + 190, 70),
             f'<path d="M{tx + 230},{ty + 150} l34,34 l-34,34" fill="none" stroke="{CYAN}" stroke-width="12" stroke-linecap="round" stroke-linejoin="round"/>',
             f'<rect x="{tx + 290}" y="{ty + 205}" width="110" height="14" fill="{PAPER}"/>',
             f'<rect x="{tx + 420}" y="{ty + 160}" width="20" height="60" fill="{CYAN}"/>']
    # the deck: two slides fanned, bottom right, reached by a second arrow
    sx, sy, sw = 560, 1190, 660
    mid = tx + tw / 2
    body += [f'<path d="M{mid},{ty + th + 10} L{mid},{sy - 70}" fill="none" stroke="{NAVY}" stroke-width="7" stroke-dasharray="20 16"/>',
             f'<path d="M{mid - 24},{sy - 84} l24,26 l24,-26" fill="none" stroke="{NAVY}" stroke-width="7" stroke-linecap="round" stroke-linejoin="round"/>',
             f'<rect x="{sx - 40}" y="{sy - 34}" width="{sw}" height="{sw * 9 / 16}" fill="#C9CCE0"/>',
             slide(sx, sy, sw, fill="#FFFFFF"),
             sparkle(tx + tw + 50, ty - 40, 30, CYAN), sparkle(330, 1040, 22, NAVY3),
             sparkle(sx + sw + 70, sy + 130, 24, CYAN)]
    return body


def write(name, body):
    svg = f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W} {H}" width="{W}" height="{H}">{"".join(body)}</svg>'
    path = os.path.join(HERE, name + ".svg")
    with open(path, "w") as f:
        f.write(svg)
    # Quick Look fits an SVG to its width, so render a square copy with the drawing centred.
    side = max(W, H)
    square = svg.replace(f'viewBox="0 0 {W} {H}" width="{W}" height="{H}"',
                         f'viewBox="{-(side - W) / 2} {-(side - H) / 2} {side} {side}" width="{side}" height="{side}"')
    if not shutil.which("qlmanage"):
        print(f"{path} written; no Quick Look, so no PNG")
        return
    from PIL import Image

    tmp = os.path.join(HERE, ".render")
    os.makedirs(tmp, exist_ok=True)
    sq = os.path.join(tmp, name + ".svg")
    with open(sq, "w") as f:
        f.write(square)
    subprocess.run(["qlmanage", "-t", "-s", str(side), "-o", tmp, sq],
                   check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    im = Image.open(os.path.join(tmp, name + ".svg.png")).convert("RGB")
    im = im.crop(((side - W) // 2, (side - H) // 2, (side + W) // 2, (side + H) // 2))
    im.save(os.path.join(HERE, name + ".png"))
    shutil.rmtree(tmp)
    print(os.path.join(HERE, name + ".png"))


if __name__ == "__main__":
    write("cover-claude-slides", cover())
    write("notes-to-deck", notes_to_deck())
