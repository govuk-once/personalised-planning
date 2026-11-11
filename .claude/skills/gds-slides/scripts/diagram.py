"""Primitives for drawing GDS-style SVG diagrams for gds-slides decks.

    import sys; sys.path.insert(0, "<skill>/scripts")
    from diagram import *
    write("flow.svg", svg(400, 300, box(...) + line(...), "Title for screen readers"))

Coordinates are SVG user units. Draw at about 400 wide for a `split` slide and 700 to 800
wide for a full-width `diagram` slide; a 13-unit label then reads close to body size.
"""

NAVY, INK, MUTED, PAPER, RULE = "#04084A", "#0B0C0C", "#505A5F", "#F8F8F8", "#B1B4B6"
FONT = 'font-family="Helvetica Neue, Helvetica, Arial, sans-serif"'

DEFS = f'''<defs>
<marker id="a" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto-start-reverse">
<path d="M0 0 L10 5 L0 10 z" fill="{INK}"/></marker></defs>'''


def esc(t):
    return t.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def text(x, y, s, size=13, weight=400, fill=INK, anchor="middle"):
    """One line of text. anchor is start, middle or end; y is the baseline."""
    return (
        f'<text x="{x}" y="{y}" {FONT} font-size="{size}" font-weight="{weight}" '
        f'fill="{fill}" text-anchor="{anchor}">{esc(s)}</text>'
    )


def box(x, y, w, h, label, sub=None, fill="#fff", fg=INK, stroke=INK, dash=None, size=13):
    """A rounded box with a bold label and an optional smaller second line."""
    d = f' stroke-dasharray="{dash}"' if dash else ""
    s = f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="6" fill="{fill}" stroke="{stroke}" stroke-width="1.5"{d}/>'
    cy = y + h / 2 + (size * 0.35 if not sub else -2)
    s += text(x + w / 2, cy, label, size, 700, fg)
    if sub:
        s += text(x + w / 2, cy + size + 2, sub, size - 2, 400, fg)
    return s


def strong(x, y, w, h, label, sub=None):
    """A navy box with white text, for the thing the diagram is about."""
    return box(x, y, w, h, label, sub, NAVY, "#fff", NAVY)


def line(x1, y1, x2, y2, dash=None, width=1.8, head=True):
    """A straight line, with an arrowhead at (x2, y2) unless head is False."""
    d = f' stroke-dasharray="{dash}"' if dash else ""
    m = ' marker-end="url(#a)"' if head else ""
    return f'<line x1="{x1}" y1="{y1}" x2="{x2}" y2="{y2}" stroke="{INK}" stroke-width="{width}"{d}{m}/>'


def area(x, y, w, h, label, dash="6 5"):
    """A dashed boundary with a label in its top left corner: a team, an account, a sandbox."""
    return (
        f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="10" fill="none" stroke="{MUTED}" '
        f'stroke-width="1.5" stroke-dasharray="{dash}"/>'
        + text(x + 14, y + 22, label, 12, 700, MUTED, "start")
    )


def group(x, y, body):
    """Move a drawing, to place small panels side by side."""
    return f'<g transform="translate({x},{y})">{body}</g>'


def svg(w, h, body, title):
    """The finished SVG. title is read by screen readers in the HTML deck."""
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {w} {h}" preserveAspectRatio="xMidYMid meet">'
        f"<title>{esc(title)}</title>{DEFS}{body}</svg>\n"
    )


def write(path, content):
    with open(path, "w") as f:
        f.write(content)
