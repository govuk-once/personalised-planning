"""Build a GDS deck from an outline: PowerPoint with python-pptx, HTML directly.

    /usr/bin/python3 build.py OUTLINE.md [--out DIR] [--format pptx,html]

OUTLINE is a Markdown outline (see slides.md and scripts/outline.py). A JSON outline in the
same shape as outline.parse() returns also works.

Writes DIR/<name>.pptx and DIR/<name>.html. With DeckCraft's deckcraft-cli installed, also
DIR/render/: one preview PNG per PowerPoint slide plus contact.png. DIR defaults to decks/<name>/ in the current directory. Prints a warning for
any text over the limits in LIMITS; a warning means cut words, not shrink type.

The template's GDS slides are sample slides, not layouts, so each slide is a copy of a sample
slide with its text replaced. SAMPLES maps slide types to those sample slides.
"""

import argparse
import base64
import glob
import json
import os
import shutil
import subprocess
import sys
import zipfile

SKILL = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TEMPLATE = os.path.join(SKILL, "template.pptx")

# 0-based index of the sample slide each type copies, in template.pptx
SAMPLES = {"title": 1, "text": 2, "quote": 2, "section": 4, "photo-section": 5, "closing": 11}
# Slide types built from parts rather than from one sample slide. Diagrams need macOS Quick Look for PowerPoint.
COMPOSED = ("table", "split", "diagram", "cards")
# Template media used by the HTML deck
MEDIA = {
    "lockup": "ppt/media/image1.png",
    "tag": "ppt/media/image2.png",
    "photo": "ppt/media/image6.jpg",
}
# Characters. Over these, the text does not fit the template's type sizes.
LIMITS = {"heading": 65, "body": 170, "bullet": 55, "bullets": 6, "section": 45, "quote": 140,
          "eyebrow": 60, "lede": 150, "callout": 120, "card": 110}
# Points, on a 720pt-wide slide. The template asks for 40 and 32; these leave more room around the text.
SIZE = {"heading": 36, "body": 24, "title": 32}
# `Density: discuss` decks are read close up, on a screen, so they carry more words at smaller sizes.
DISCUSS = {"heading": 26, "body": 16, "section": 48}
# Scorecard tags in tables: the word always shows, so colour is never the only signal.
TAGS = {"yes": ("Yes", "04084A", "FFFFFF"), "partly": ("Partly", "D9DBE8", "04084A"), "no": ("No", "E3E3E3", "383838")}
CARD, TINT, HIGHLIGHT = "ECECEE", "E6E7EF", "ECEDF4"  # card panel, callout band, highlighted table column


def find_cli():
    for c in (
        os.environ.get("DECKCRAFT_CLI"),
        shutil.which("deckcraft-cli"),
        os.path.expanduser("~/.local/bin/deckcraft-cli"),
    ):
        if c and os.path.exists(c):
            return c
    return None


def cli():
    return find_cli() or sys.exit(
        "deckcraft-cli not found. Install it to ~/.local/bin or set DECKCRAFT_CLI."
    )


def expand(outline):
    """The outline's slides with the title and closing slides added: [(type, heading, lines, notes, slide)]."""
    p = outline["presenter"]
    who = [p["name"], p["role"], p.get("org", "Government Digital Service")]
    slides = [("title", None, [outline["title"]] + who, outline.get("notes", ""), {})]
    for s in outline["slides"]:
        body = s.get("bullets") or ([s["body"]] if s.get("body") else [])
        slides.append((s["type"], s.get("heading"), body, s.get("notes", ""), s))
    slides.append(("closing", None, [outline.get("closing", "Thanks!"), ""] + who, "", {}))
    return slides


def limits(sizes):
    """LIMITS at the deck's sizes: line length grows with smaller type, and so does the number of lines."""
    k, kh = SIZE["body"] / sizes["body"], SIZE["heading"] / sizes["heading"]
    out = {key: int(v * k * k) for key, v in LIMITS.items() if key in ("body", "quote", "lede", "callout", "card")}
    out.update(heading=int(LIMITS["heading"] * kh), bullet=int(LIMITS["bullet"] * k),
               bullets=int(LIMITS["bullets"] * k), eyebrow=int(LIMITS["eyebrow"] * k), section=LIMITS["section"])
    return out


def check(slides, sizes):
    warn = []
    lim = limits(sizes)
    # Composed types have one line for the heading: the frame's width at about 0.5em a character.
    one_line = int(FRAME["heading"][2] / (sizes["heading"] * 0.5))
    for n, (kind, head, body, _, s) in enumerate(slides, 1):
        for key in ("eyebrow", "callout"):
            if len(s.get(key, "")) > lim[key]:
                warn.append(f"slide {n}: {key} {len(s[key])} chars, limit {lim[key]}")
        if kind in ("cards", "table") and len(s.get("body", "")) > lim["lede"]:
            warn.append(f"slide {n}: lede {len(s['body'])} chars, limit {lim['lede']}")
        if kind == "cards":
            # Narrower cards hold less: the limit is for three across.
            cap = int(lim["card"] * 3 / max(3, len(s["blocks"])))
            for b in s["blocks"]:
                words = len(b.get("text", "") or " ".join(b.get("bullets", []))) + len(b.get("evidence", ""))
                if words > cap:
                    warn.append(f"slide {n}: card {b['label'][:25]!r} {words} chars, limit {cap}")
        if kind in COMPOSED:
            if len(head or "") > one_line:
                warn.append(f"slide {n}: {kind} heading {len(head)} chars, one line is {one_line} at this size")
            continue
        if kind not in SAMPLES:
            sys.exit(
                f"Slide {n}: unknown type {kind!r}. Use one of {sorted(SAMPLES) + list(COMPOSED)}."
            )
        if kind in ("section", "photo-section"):
            if len(head or "") > lim["section"]:
                warn.append(
                    f"slide {n}: section heading {len(head)} chars, limit {lim['section']}"
                )
        elif kind == "quote":
            if len(s.get("quote", "")) > lim["quote"]:
                warn.append(f"slide {n}: quote {len(s['quote'])} chars, limit {lim['quote']}")
        elif kind == "text":
            if len(head or "") > lim["heading"]:
                warn.append(f"slide {n}: heading {len(head)} chars, limit {lim['heading']}")
            if len(body) > lim["bullets"]:
                warn.append(f"slide {n}: {len(body)} bullets, limit {lim['bullets']}")
            for b in body if len(body) > 1 else []:
                if len(b) > lim["bullet"]:
                    warn.append(
                        f"slide {n}: bullet {len(b)} chars, limit {lim['bullet']}: {b[:30]}..."
                    )
            if len(body) == 1 and len(body[0]) > lim["body"]:
                warn.append(f"slide {n}: body {len(body[0])} chars, limit {lim['body']}")
    return warn


# Slide points (720 x 405) for the composed types in PowerPoint.
FRAME = {"heading": [43, 26, 634, 64], "top": 100, "bottom": 355, "left": 43, "width": 634}
FONT = "Helvetica Neue"
INK, NAVY, RULE, MUTED = "0B0C0C", "04084A", "CBCBCB", "434343"
NO_STYLE = "{2D5ABB26-0587-4C30-8999-92F81FD0307C}"  # PowerPoint's "No Style, No Grid" table style


def picture(base, s, folder):
    """The slide's SVG as a PNG on the slide background, through Quick Look. Returns (path, aspect)."""
    import re

    try:
        from PIL import Image
    except ImportError:
        sys.exit(
            "Diagrams in PowerPoint need Pillow. Run scripts/check.py, or build --format html."
        )
    if not shutil.which("qlmanage"):
        sys.exit(
            "Diagrams in PowerPoint need macOS Quick Look (qlmanage). Build --format html on other systems."
        )
    with open(os.path.join(base, s["diagram"])) as f:
        art = f.read()
    w, h = map(float, re.search(r'viewBox="0 0 ([\d.]+) ([\d.]+)"', art).groups())
    art = re.sub(
        r"(<svg[^>]*>)", r'\1<rect width="100%" height="100%" fill="#F8F8F8"/>', art, count=1
    )
    stem = os.path.splitext(os.path.basename(s["diagram"]))[0]
    src = os.path.join(folder, stem + ".svg")
    with open(src, "w") as f:
        f.write(art)
    subprocess.run(
        ["qlmanage", "-t", "-s", "2400", "-o", folder, src],
        check=True,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    im = Image.open(src + ".png").convert("RGB")
    k = 2400 / max(w, h)
    cw, ch = w * k, h * k
    im = im.crop(
        (int((2400 - cw) / 2), int((2400 - ch) / 2), int((2400 + cw) / 2), int((2400 + ch) / 2))
    )
    out = os.path.join(folder, stem + ".png")
    im.save(out)
    return out, w / h


def copy_slide(prs, src):
    """A copy of a sample slide at the end of the deck: its shapes, background and images."""
    import copy

    from pptx.opc.constants import RELATIONSHIP_TYPE as RT

    dst = prs.slides.add_slide(src.slide_layout)
    tree = dst.shapes._spTree
    for el in list(tree)[2:]:  # keep nvGrpSpPr and grpSpPr, drop the layout's placeholders
        tree.remove(el)
    ids = {}
    for rid, rel in src.part.rels.items():
        if rel.reltype in (RT.NOTES_SLIDE, RT.SLIDE_LAYOUT):
            continue
        ids[rid] = (
            dst.part.relate_to(rel.target_ref, rel.reltype, is_external=True)
            if rel.is_external
            else dst.part.relate_to(rel.target_part, rel.reltype)
        )
    for el in list(src.shapes._spTree)[2:]:
        tree.append(copy.deepcopy(el))
    bg = src._element.cSld.bg
    if bg is not None:
        dst._element.cSld.insert(0, copy.deepcopy(bg))
    r = "{http://schemas.openxmlformats.org/officeDocument/2006/relationships}"
    for el in dst._element.iter():
        for attr in (r + "embed", r + "id", r + "link"):
            if el.get(attr) in ids:
                el.set(attr, ids[el.get(attr)])
    return dst


def drop_slides(prs, count):
    """Remove the first `count` slides: the template's samples, once copied."""
    ids = prs.slides._sldIdLst
    for sld in list(ids)[:count]:
        prs.part.drop_rel(sld.rId)
        ids.remove(sld)


def paragraphs(frame, paras):
    """Replace a text frame's text. Each para: dict(text, size, bold=False, color=INK or None,
    bullet=False, indent=16, after=0, rpr=None), where rpr is a run-properties element to copy."""
    import copy

    from lxml import etree
    from pptx.oxml.ns import qn

    body = frame._txBody
    for p in body.findall(qn("a:p")):
        body.remove(p)
    for para in paras:
        p = etree.SubElement(body, qn("a:p"))
        hang = para.get("indent", 16) * 12700 if para.get("bullet") else 0
        ppr = etree.SubElement(
            p, qn("a:pPr"), marL=str(int(hang)), indent=str(int(-hang)), algn="l"
        )
        etree.SubElement(etree.SubElement(ppr, qn("a:spcBef")), qn("a:spcPts"), val="0")
        etree.SubElement(
            etree.SubElement(ppr, qn("a:spcAft")),
            qn("a:spcPts"),
            val=str(int(para.get("after", 0) * 100)),
        )
        if para.get("bullet"):
            etree.SubElement(ppr, qn("a:buChar"), char="•")
        else:
            etree.SubElement(ppr, qn("a:buNone"))
        if para.get("rpr") is not None:
            rpr = copy.deepcopy(para["rpr"])
            rpr.tag = qn("a:rPr")
            if para.get("size"):
                rpr.set("sz", str(int(round(para["size"] * 100))))
        else:
            rpr = etree.Element(
                qn("a:rPr"),
                lang="en-GB",
                sz=str(int(round(para["size"] * 100))),
                b="1" if para.get("bold") else "0",
            )
            color = para.get("color", INK)
            if color:
                fill = etree.SubElement(rpr, qn("a:solidFill"))
                etree.SubElement(fill, qn("a:srgbClr"), val=color)
            if para.get("highlight"):  # after the fill and before the fonts, as the schema orders them
                mark = etree.SubElement(rpr, qn("a:highlight"))
                etree.SubElement(mark, qn("a:srgbClr"), val=para["highlight"])
            for tag in ("a:latin", "a:ea", "a:cs", "a:sym"):
                etree.SubElement(rpr, qn(tag), typeface=FONT)
        # "runs": [(text, bold)] for a paragraph with a bold lead-in; otherwise one run.
        runs = para.get("runs") or ([(para["text"], None)] if para["text"] else [])
        for text, bold in runs:
            run = etree.SubElement(p, qn("a:r"))
            r = copy.deepcopy(rpr)
            if bold is not None:
                r.set("b", "1" if bold else "0")
            run.append(r)
            etree.SubElement(run, qn("a:t")).text = text
        if not runs:
            end = copy.deepcopy(rpr)
            end.tag = qn("a:endParaRPr")
            p.append(end)


def text_height(text, size, width):
    """Points of height for text at this size in this width, at about half an em a character."""
    per_line = max(1, int(width / (size * 0.5)))
    return -(-len(text) // per_line) * size * 1.22


def split_lead(text):
    """'**Bold lead.** The rest' -> ('Bold lead.', 'The rest'); otherwise ('', text)."""
    import re

    m = re.match(r"\*\*(.+?)\*\*\s*(.*)$", text)
    return (m.group(1), m.group(2)) if m else ("", text)


def tag_cell(value):
    """'[yes] a snapshot of the real one' -> ('yes', 'a snapshot of the real one'); else (None, None)."""
    import re

    m = re.match(r"\[(yes|partly|no)\]\s*(.*)$", value.strip(), re.IGNORECASE)
    return (m.group(1).lower(), m.group(2)) if m else (None, None)


def scorecard_header(columns):
    """Header cells with '{highlight}' removed, and the indexes of the columns it marked."""
    marked = [i for i, c in enumerate(columns) if c.rstrip().endswith("{highlight}")]
    return [c.replace("{highlight}", "").strip() for c in columns], marked


def cell_borders(cell, bottom, width, fill=None):
    """No lines except a bottom rule, and no fill unless given, in the order PowerPoint expects."""
    from lxml import etree
    from pptx.oxml.ns import qn

    tc = cell._tc
    old = tc.find(qn("a:tcPr"))
    tcpr = etree.SubElement(
        tc, qn("a:tcPr"), marL="0", marR=str(8 * 12700), marT=str(3 * 12700), marB=str(3 * 12700)
    )
    if old is not None:
        tc.remove(old)
    for side in ("a:lnL", "a:lnR", "a:lnT", "a:lnB"):
        ln = etree.SubElement(tcpr, qn(side), w=str(int(width * 12700)) if side == "a:lnB" else "0")
        if side == "a:lnB":
            etree.SubElement(etree.SubElement(ln, qn("a:solidFill")), qn("a:srgbClr"), val=bottom)
        else:
            etree.SubElement(ln, qn("a:noFill"))
    if fill:
        tcpr.set("marL", str(6 * 12700))
        etree.SubElement(etree.SubElement(tcpr, qn("a:solidFill")), qn("a:srgbClr"), val=fill)
    else:
        etree.SubElement(tcpr, qn("a:noFill"))


def build_pptx(slides, path, sizes, base):
    from pptx import Presentation
    from pptx.dml.color import RGBColor
    from pptx.enum.text import MSO_ANCHOR
    from pptx.oxml.ns import qn
    from pptx.util import Pt

    prs = Presentation(TEMPLATE)
    samples = len(prs.slides)
    src = list(prs.slides)
    art = os.path.join(os.path.dirname(path), "render", "diagrams")

    def add_text(slide, x, y, w, h, paras):
        box = slide.shapes.add_textbox(Pt(x), Pt(y), Pt(w), Pt(h))
        frame = box.text_frame
        frame.word_wrap = True
        frame.vertical_anchor = MSO_ANCHOR.TOP
        frame.margin_left = frame.margin_right = frame.margin_top = frame.margin_bottom = 0
        paragraphs(frame, paras)
        return box

    def rect(slide, x, y, w, h, color):
        shape = slide.shapes.add_shape(1, Pt(x), Pt(y), Pt(w), Pt(h))  # 1: rectangle
        shape.fill.solid()
        shape.fill.fore_color.rgb = RGBColor.from_string(color)
        shape.line.fill.background()
        shape.shadow.inherit = False
        return shape

    def callout(slide, text, x, y, w, h, size):
        """A tinted band with a navy rule on the left; a **bold** opening phrase stays bold."""
        rect(slide, x, y, w, h, TINT)
        rect(slide, x, y, 5, h, NAVY)
        lead, rest = split_lead(text)
        runs = ([(lead + " ", True)] if lead else []) + [(rest, False)]
        add_text(slide, x + 17, y + 7, w - 30, h - 14, [{"text": text, "size": size, "runs": runs}])

    def cards(slide, s, top, bottom):
        """Two to four panels across, each with a navy top rule: number, title, text, evidence."""
        blocks = s["blocks"]
        n, gap, pad = len(blocks), 12, 11
        cw = (FRAME["width"] - gap * (n - 1)) / n
        inner = cw - 2 * pad
        sets = []
        for i, b in enumerate(blocks):
            paras = []
            if s.get("numbered"):
                paras.append({"text": str(i + 1), "size": sizes["heading"] * 0.85, "bold": True,
                              "color": NAVY, "after": 4})
            paras.append({"text": b["label"], "size": sizes["body"] * 0.88, "bold": True, "after": 4})
            items = b.get("bullets") or ([b["text"]] if b.get("text") else [])
            paras += [{"text": t, "size": sizes["body"] * 0.76, "bullet": bool(b.get("bullets")),
                       "indent": 10, "after": 3} for t in items]
            if b.get("evidence"):
                paras[-1]["after"] = 8
                paras.append({"text": b["evidence"], "size": sizes["body"] * 0.66, "color": MUTED})
            sets.append(paras)
        need = max(sum(text_height(p["text"], p["size"], inner) + p.get("after", 0) for p in ps) for ps in sets)
        h = min(bottom - top, need * 1.08 + 2 * pad + 4)
        for i, paras in enumerate(sets):
            x = FRAME["left"] + i * (cw + gap)
            rect(slide, x, top, cw, h, CARD)
            rect(slide, x, top, cw, 4, NAVY)
            add_text(slide, x + pad, top + pad + 4, inner, h - 2 * pad - 4, paras)
        return top + h

    def place(slide, s, x, y, w, h):
        os.makedirs(art, exist_ok=True)
        png, aspect = picture(base, s, art)
        pw, ph = (w, w / aspect) if w / aspect <= h else (h * aspect, h)
        pic = slide.shapes.add_picture(
            png, Pt(x + (w - pw) / 2), Pt(y + (h - ph) / 2), Pt(pw), Pt(ph)
        )
        pic._element.nvPicPr.cNvPr.set("descr", s.get("alt", ""))

    def text_box(slide, s, x, y, w, h):
        """Lead sentence and labelled blocks as one text box."""
        b = sizes["body"] * 0.92
        paras = [{"text": s["body"], "size": b}] if s.get("body") else []
        for blk in s.get("blocks", []):
            paras.append(
                {
                    "text": blk["label"],
                    "size": sizes["body"] * 0.8,
                    "bold": True,
                    "color": NAVY,
                    "after": 3,
                }
            )
            paras += [
                {"text": t, "size": b, "bullet": bool(blk.get("bullets")), "after": 4}
                for t in ([blk["text"]] if blk.get("text") else blk["bullets"])
            ]
            paras[-1]["after"] = 10
        if not paras:
            return
        box = slide.shapes.add_textbox(Pt(x), Pt(y), Pt(w), Pt(h))
        frame = box.text_frame
        frame.word_wrap = True
        frame.margin_left = frame.margin_right = frame.margin_top = frame.margin_bottom = 0
        paragraphs(frame, paras)

    def table(slide, t, y):
        head, hl = scorecard_header(t["columns"])
        rows = [head] + t["rows"]
        cols = len(head)
        noted = [any(tag_cell(c)[1] for c in r) for r in rows]
        heights = [20 + (11 if n else 0) for n in noted]
        frame = slide.shapes.add_table(
            len(rows), cols, Pt(FRAME["left"]), Pt(y), Pt(FRAME["width"]), Pt(sum(heights))
        )
        tbl = frame.table
        pr = frame._element.graphic.graphicData.tbl.tblPr
        pr.set("firstRow", "0")
        pr.set("bandRow", "0")
        style = pr.find(qn("a:tableStyleId"))
        if style is None:
            from lxml import etree

            style = etree.SubElement(pr, qn("a:tableStyleId"))
        style.text = NO_STYLE
        first = FRAME["width"] * 0.34
        tbl.columns[0].width = Pt(first)
        for c in range(1, cols):
            tbl.columns[c].width = Pt((FRAME["width"] - first) / (cols - 1))
        size = sizes["body"] * 0.78
        for r, row in enumerate(rows):
            tbl.rows[r].height = Pt(heights[r])
            for c, value in enumerate(row):
                cell = tbl.cell(r, c)
                tag, note = tag_cell(value) if r else (None, None)
                if tag:
                    word, back, fore = TAGS[tag]
                    paras = [{"text": f" {word} ", "size": size * 0.92, "bold": True,
                              "color": fore, "highlight": back, "after": 2}]
                    if note:
                        paras.append({"text": note, "size": size * 0.8, "color": MUTED})
                else:
                    paras = [{"text": value, "size": size, "bold": r == 0 or c == 0}]
                paragraphs(cell.text_frame, paras)
                cell_borders(cell, NAVY if r == 0 else RULE, 1.5 if r == 0 else 0.75,
                             HIGHLIGHT if c in hl else None)
        return y + sum(heights)

    for kind, *_ in slides:
        copy_slide(prs, src[SAMPLES.get(kind, SAMPLES["text"])])
    drop_slides(prs, samples)

    assert len(prs.slides) == len(slides)
    for i, slide in enumerate(prs.slides):
        kind, head, body, notes, s = slides[i]
        texts = [sh for sh in slide.shapes if sh.has_text_frame]
        if kind == "title":
            # The first text box is the template's "add a classification" prompt; the master already marks OFFICIAL.
            texts[0]._element.getparent().remove(texts[0]._element)
        box = texts[-1]
        if kind in ("title", "closing"):
            strong = {0} | ({2} if kind == "closing" else set())
            paragraphs(
                box.text_frame,
                [
                    {"text": t, "size": SIZE["title"], "bold": n in strong, "color": None}
                    for n, t in enumerate(body)
                ],
            )
        elif kind in ("section", "photo-section"):
            rpr = box._element.find(".//" + qn("a:rPr"))
            size = sizes["section"] if sizes["section"] != 72 else None
            paragraphs(box.text_frame, [{"text": head, "size": size, "rpr": rpr}])
        elif kind == "quote":
            # Callout: the quote large and navy, set off by a navy rule, with an optional attribution.
            q = sizes["heading"] * 0.8
            attr = s.get("attribution")
            paras = [{"text": s["quote"], "size": q, "bold": True, "color": NAVY, "after": 12 if attr else 0}]
            if attr:
                paras.append({"text": attr, "size": sizes["body"] * 0.72, "color": MUTED})
            left, width = FRAME["left"] + 24, FRAME["width"] - 24
            box.left, box.width = Pt(left), Pt(width)
            frame = box.text_frame
            frame.margin_left = frame.margin_right = 0
            paragraphs(frame, paras)
            # The text box is centred vertically, so the rule is sized to an estimate of the text's height.
            lines = -(-len(s["quote"]) // int(width / (q * 0.52)))
            h = lines * q * 1.2 + (12 + sizes["body"] * 0.72 * 1.3 if attr else 0)
            mid = (box.top + box.height / 2) / 12700
            bar = slide.shapes.add_shape(1, Pt(FRAME["left"]), Pt(mid - h / 2), Pt(6), Pt(h))
            bar.fill.solid()
            bar.fill.fore_color.rgb = RGBColor.from_string(NAVY)
            bar.line.fill.background()
        elif kind == "text" and not s.get("callout"):
            size = sizes["body"] * 0.86 if len(body) > 5 else sizes["body"]
            eyebrow = s.get("eyebrow")
            paragraphs(
                box.text_frame,
                ([{"text": eyebrow, "size": sizes["body"] * 0.72, "color": MUTED, "after": 6}] if eyebrow else [])
                + [{"text": head, "size": sizes["heading"], "bold": True, "after": 14}]
                + [
                    {"text": t, "size": size, "bullet": len(body) > 1, "indent": 22, "after": 4}
                    for t in body
                ],
            )
        else:
            # Heading in the template's text box, moved to the top; the rest stacked below it:
            # eyebrow, heading, callout (top), lede, content, callout (bottom).
            left, width = FRAME["left"], FRAME["width"]
            y = 28
            if s.get("eyebrow"):
                e = sizes["body"] * 0.72
                add_text(slide, left, y, width, e * 1.3, [{"text": s["eyebrow"], "size": e, "color": MUTED}])
                y += e * 1.3 + 2
            # Text slides moved here by a callout can have a two-line heading; the others have one.
            hh = text_height(head, sizes["heading"], width) * 1.02 if kind == "text" else sizes["heading"] * 1.25
            paragraphs(box.text_frame, [{"text": head, "size": sizes["heading"], "bold": True}])
            if s.get("eyebrow") or kind == "text":
                box.left, box.top, box.width, box.height = Pt(left), Pt(y), Pt(width), Pt(hh)
                frame = box.text_frame
                frame.vertical_anchor = MSO_ANCHOR.TOP
                frame.margin_left = frame.margin_right = frame.margin_top = frame.margin_bottom = 0
                top = max(FRAME["top"], y + hh + sizes["heading"] * 0.45)
            else:
                # Without an eyebrow, the heading sits exactly where it always has.
                box.left, box.top, box.width, box.height = (Pt(v) for v in FRAME["heading"])
                top = FRAME["top"]
            bottom = FRAME["bottom"]
            after = None  # a bottom callout, drawn once the content's foot is known
            if s.get("callout"):
                cs = sizes["body"] * 0.78
                ch = text_height(s["callout"], cs, width - 30) + 14
                if s.get("callout_at") == "top":
                    callout(slide, s["callout"], left, top, width, ch, cs)
                    top += ch + 10
                else:
                    bottom -= ch + 10
                    after = (ch, cs)
            if kind in ("table", "cards") and s.get("body"):
                ls = sizes["body"] * 0.88
                lh = text_height(s["body"], ls, width)
                add_text(slide, left, top, width, lh, [{"text": s["body"], "size": ls}])
                top += lh + 10
            foot = bottom  # where the content ends: known for tables and cards, the frame otherwise
            if kind == "table":
                foot = table(slide, s["table"], top)
            elif kind == "cards":
                foot = cards(slide, s, top, bottom)
            elif kind == "text":
                size = sizes["body"] * 0.86 if len(body) > 5 else sizes["body"]
                add_text(slide, left, top, width, bottom - top, [
                    {"text": t, "size": size, "bullet": len(body) > 1, "indent": 22, "after": 4} for t in body
                ])
            elif kind == "split":
                half = (width - 36) / 2
                text_box(slide, s, left, top, half, bottom - top)
                place(slide, s, left + half + 36, top, half, bottom - top)
            else:
                lead = 34 if s.get("body") else 0
                text_box(slide, s, left, top, width, lead)
                place(slide, s, left, top + lead, width, bottom - top - lead)
            if after:
                callout(slide, s["callout"], left, min(foot, bottom) + 10, width, *after)
        if notes:
            slide.notes_slide.notes_text_frame.text = notes
    prs.save(path)


def render(pptx, folder):
    os.makedirs(folder, exist_ok=True)
    for old in glob.glob(os.path.join(folder, "slide-*.png")):
        os.remove(old)
    subprocess.run(
        [cli(), "render", pptx, "--all", "--scale", "1", folder],
        check=True,
        stdout=subprocess.DEVNULL,
    )
    try:
        from PIL import Image
    except ImportError:
        return None
    ims = [Image.open(f) for f in sorted(glob.glob(os.path.join(folder, "slide-*.png")))]
    w, h = ims[0].size
    rows = (len(ims) + 1) // 2
    sheet = Image.new("RGB", (2 * w + 10, rows * (h + 10)), "grey")
    for i, im in enumerate(ims):
        sheet.paste(im, ((i % 2) * (w + 10), (i // 2) * (h + 10)))
    out = os.path.join(folder, "contact.png")
    sheet.save(out)
    return out


def esc(t):
    return t.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def svg(base, s):
    """The slide's diagram, inlined so the deck stays one file."""
    with open(os.path.join(base, s["diagram"])) as f:
        art = f.read()
    art = art[art.index("<svg") :]
    alt = esc(s.get("alt", ""))
    return f'<figure class="diagram" role="img" aria-label="{alt}">{art}</figure>'


def blocks(s):
    html = f'<p class="lead">{esc(s["body"])}</p>' if s.get("body") else ""
    for b in s.get("blocks", []):
        html += f'<div class="block"><h3>{esc(b["label"])}</h3>'
        if b.get("bullets"):
            html += "<ul>" + "".join(f"<li>{esc(t)}</li>" for t in b["bullets"]) + "</ul>"
        else:
            html += f"<p>{esc(b.get('text', ''))}</p>"
        html += "</div>"
    return html


def table(t):
    columns, hl = scorecard_header(t["columns"])

    def cell(c, value):
        tag, note = tag_cell(value)
        if tag:
            word = TAGS[tag][0]
            value_html = f'<span class="tg {tag}">{word}</span>' + (f'<span class="tnote">{esc(note)}</span>' if note else "")
        else:
            value_html = esc(value)
        return f"<td{' class=hl' if c in hl else ''}>{value_html}</td>"

    head = "".join(f"<th{' class=hl' if i in hl else ''}>{esc(c)}</th>" for i, c in enumerate(columns))
    rows = "".join("<tr>" + "".join(cell(c, v) for c, v in enumerate(r)) + "</tr>" for r in t["rows"])
    return f"<table><thead><tr>{head}</tr></thead><tbody>{rows}</tbody></table>"


def eyebrow(s):
    return f'<p class="eyebrow">{esc(s["eyebrow"])}</p>' if s.get("eyebrow") else ""


def callout_html(s, where):
    if not s.get("callout") or s.get("callout_at", "top") != where:
        return ""
    lead, rest = split_lead(s["callout"])
    lead = f"<strong>{esc(lead)}</strong> " if lead else ""
    return f'<div class="callout {where}">{lead}{esc(rest)}</div>'


def cards_html(s):
    out = []
    for i, b in enumerate(s["blocks"], 1):
        num = f'<span class="cnum">{i}</span>' if s.get("numbered") else ""
        if b.get("bullets"):
            text = "<ul>" + "".join(f"<li>{esc(t)}</li>" for t in b["bullets"]) + "</ul>"
        else:
            text = f"<p>{esc(b.get('text', ''))}</p>"
        ev = f'<p class="evidence">{esc(b["evidence"])}</p>' if b.get("evidence") else ""
        out.append(f'<div class="card">{num}<h3>{esc(b["label"])}</h3>{text}{ev}</div>')
    return f'<div class="cards" style="--n: {len(out)}">{"".join(out)}</div>'


def deck_sizes(outline):
    """Type sizes in points, with the outline's optional `sizes` over the template's."""
    base = {"heading": SIZE["heading"], "body": SIZE["body"], "section": 72}
    if outline.get("density", "present").lower() == "discuss":
        base.update(DISCUSS)
    return {**base, **outline.get("sizes", {})}


def build_html(slides, outline, path, base):
    z = zipfile.ZipFile(TEMPLATE)
    uri = {
        k: f"data:image/{v.rsplit('.', 1)[1].replace('jpg', 'jpeg')};base64,"
        + base64.b64encode(z.read(v)).decode()
        for k, v in MEDIA.items()
    }
    marking = outline.get("marking", "OFFICIAL")
    # The lockup and tag are CSS backgrounds, defined once, so each slide doesn't carry its own copy.
    lockup = '<span class="lockup" role="img" aria-label="Government Digital Service, Department for Digital, Culture, Media and Sport"></span>'
    out = []
    for n, (kind, head, body, notes, s) in enumerate(slides, 1):
        foot = f'<span class="tag" role="img" aria-label="GDS"></span><span class="num">{n}</span>'
        if kind in ("title", "closing"):
            strong = {0} | ({2} if kind == "closing" else set())
            lines = "".join(
                f"<p{' class=strong' if i in strong else ''}>{esc(t) or '&nbsp;'}</p>"
                for i, t in enumerate(body)
            )
            inner, cls, foot = f'{lockup}<div class="text">{lines}</div>', "title", ""
        elif kind in ("section", "photo-section"):
            inner, cls = f'<div class="text"><h1>{esc(head)}</h1></div>', kind
        elif kind == "quote":
            attr = f"<footer>{esc(s['attribution'])}</footer>" if s.get("attribution") else ""
            inner = f'<div class="text"><blockquote><p>{esc(s["quote"])}</p>{attr}</blockquote></div>'
            cls = ""
        elif kind in COMPOSED:
            lede = f'<p class="lede">{esc(s["body"])}</p>' if s.get("body") and kind in ("table", "cards") else ""
            if kind == "table":
                content = table(s["table"])
            elif kind == "cards":
                content = cards_html(s)
            elif kind == "split":
                content = f'<div class="cols"><div class="col">{blocks(s)}</div>{svg(base, s)}</div>'
            else:
                content = blocks(s) + svg(base, s)
            inner = (
                f'<div class="text top">{eyebrow(s)}<h2>{esc(head)}</h2>{callout_html(s, "top")}'
                f'{lede}{content}{callout_html(s, "bottom")}</div>'
            )
            cls = "wide"
        else:
            if len(body) > 1:
                text = "<ul>" + "".join(f"<li>{esc(b)}</li>" for b in body) + "</ul>"
            else:
                text = "".join(f"<p>{esc(b)}</p>" for b in body)
            inner = (
                f'<div class="text{" dense" if len(body) > 5 else ""}">{eyebrow(s)}<h2>{esc(head)}</h2>'
                f'{callout_html(s, "top")}{text}{callout_html(s, "bottom")}</div>'
            )
            cls = ""
        out.append(
            f'<section class="slide {cls}" aria-label="Slide {n}">'
            f'<div class="marking">{esc(marking)}</div>{inner}{foot}</section>'
        )
        if notes:
            out.append(
                f'<aside class="notes" data-slide="{n - 1}" aria-label="Speaker notes, slide {n}">'
                f"<p>{esc(notes)}</p></aside>"
            )
    sizes = deck_sizes(outline)
    html = HTML.replace("{{title}}", esc(outline["title"])).replace("{{photo}}", uri["photo"])
    html = html.replace("{{tag}}", uri["tag"]).replace("{{lockup}}", uri["lockup"])
    html = html.replace(
        "{{sizes}}", f"--h: {sizes['heading']}; --b: {sizes['body']}; --s: {sizes['section']};"
    )
    html = html.replace("{{slides}}", "\n".join(out))
    with open(path, "w") as f:
        f.write(html)


HTML = """<!doctype html>
<html lang="en-GB">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{{title}}</title>
<style>
  /* From the GDS 2025 slide template: 10 x 5.625 in slide, 720 pt wide. */
  :root { --paper: #F8F8F8; --navy: #04084A; --ink: #0B0C0C; --muted: #434343; --rule: #CBCBCB;
          --font: "Helvetica Neue", Helvetica, Arial, sans-serif; {{sizes}} }
  * { box-sizing: border-box; margin: 0; padding: 0; }
  html, body { height: 100%; background: #1d1d1d; font-family: var(--font); }
  .deck { display: flex; flex-direction: column; align-items: center; gap: 24px; padding: 24px 16px; }
  .slide { -webkit-print-color-adjust: exact; print-color-adjust: exact; position: relative; width: min(100%, 1280px); aspect-ratio: 16 / 9; background: var(--paper);
           color: var(--ink); overflow: hidden; container-type: inline-size; --pt: calc(100cqw / 720); }
  .marking { position: absolute; top: calc(6 * var(--pt)); left: 0; right: 0; text-align: center;
             font-size: calc(7 * var(--pt)); letter-spacing: .04em; color: var(--muted); z-index: 1; }
  .tag { position: absolute; left: 2%; top: 90.7%; width: 9%; aspect-ratio: 2048 / 701; z-index: 1;
         background: url("{{tag}}") center / contain no-repeat; }
  .lockup { position: absolute; left: 5%; top: 9%; width: 43%; aspect-ratio: 2048 / 616;
            background: url("{{lockup}}") center / contain no-repeat; }
  .num { position: absolute; right: 3%; bottom: 3%; font-size: calc(9 * var(--pt)); color: var(--muted); z-index: 1; }
  .text { position: absolute; left: 6%; top: 9%; width: 89%; height: 80%; z-index: 1;
          display: flex; flex-direction: column; justify-content: center; }
  h1, h2 { font-weight: 700; line-height: 1.15; }
  h2 { font-size: calc(var(--h) * var(--pt)); margin-bottom: calc(var(--h) * .45 * var(--pt)); }
  .text p, .text li { font-size: calc(var(--b) * var(--pt)); line-height: 1.3; }
  .text ul { list-style: none; }
  .text li { padding-left: calc(var(--b) * .8 * var(--pt)); position: relative; margin-bottom: calc(var(--b) * .3 * var(--pt)); }
  .text li::before { content: "\\2022"; position: absolute; left: 0; }
  .dense li { font-size: calc(var(--b) * .86 * var(--pt)); margin-bottom: calc(2 * var(--pt)); }
  blockquote { border-left: calc(6 * var(--pt)) solid var(--navy); padding-left: calc(18 * var(--pt)); }
  blockquote p { font-size: calc(var(--h) * .8 * var(--pt)) !important; font-weight: 700; color: var(--navy); line-height: 1.2 !important; }
  blockquote footer { font-size: calc(var(--b) * .72 * var(--pt)); color: var(--muted); margin-top: calc(12 * var(--pt)); }
  /* Composed types: table, split (text beside a diagram) and diagram. */
  .wide .text.top { top: 11%; height: 76%; justify-content: flex-start; }
  .text p.lead { margin-bottom: calc(var(--b) * .8 * var(--pt)); }
  .block { margin-bottom: calc(var(--b) * .8 * var(--pt)); }
  .block h3 { font-size: calc(var(--b) * .8 * var(--pt)); font-weight: 700; color: var(--navy);
              margin-bottom: calc(3 * var(--pt)); }
  .cols { display: grid; grid-template-columns: 1fr 1fr; gap: calc(36 * var(--pt)); flex: 1; min-height: 0; }
  .col p, .col li { font-size: calc(var(--b) * .92 * var(--pt)); }
  .diagram { flex: 1; min-height: 0; display: flex; align-items: center; justify-content: center; }
  .diagram svg { width: 100%; height: 100%; }
  table { border-collapse: collapse; width: 100%; font-size: calc(var(--b) * .78 * var(--pt)); line-height: 1.3; }
  th { text-align: left; font-weight: 700; border-bottom: calc(2 * var(--pt)) solid var(--navy);
       padding: 0 calc(10 * var(--pt)) calc(5 * var(--pt)) 0; }
  td { vertical-align: top; border-bottom: 1px solid var(--rule); padding: calc(4.5 * var(--pt)) calc(10 * var(--pt)) calc(4.5 * var(--pt)) 0; }
  td:first-child { font-weight: 700; width: 34%; }
  /* Eyebrow, lede, callout, cards and scorecard tags. */
  .text p.eyebrow { font-size: calc(var(--b) * .72 * var(--pt)); color: var(--muted); margin-bottom: calc(4 * var(--pt)); }
  .text p.lede { font-size: calc(var(--b) * .88 * var(--pt)); margin-bottom: calc(10 * var(--pt)); }
  .callout { border-left: calc(5 * var(--pt)) solid var(--navy); background: #E6E7EF;
             padding: calc(7 * var(--pt)) calc(12 * var(--pt)); font-size: calc(var(--b) * .78 * var(--pt)); line-height: 1.3; }
  .callout.top { margin-bottom: calc(10 * var(--pt)); }
  .callout.bottom { margin-top: calc(10 * var(--pt)); }
  .cards { display: grid; grid-template-columns: repeat(var(--n), minmax(0, 1fr)); gap: calc(12 * var(--pt)); }
  .card { background: #ECECEE; border-top: calc(4 * var(--pt)) solid var(--navy); padding: calc(11 * var(--pt)); }
  .card h3 { font-size: calc(var(--b) * .88 * var(--pt)); font-weight: 700; margin-bottom: calc(4 * var(--pt)); line-height: 1.2; }
  .text .card p, .text .card li { font-size: calc(var(--b) * .76 * var(--pt)); line-height: 1.3; }
  .text .card li { padding-left: calc(var(--b) * .5 * var(--pt)); margin-bottom: calc(2 * var(--pt)); }
  .cnum { display: block; font-size: calc(var(--h) * .85 * var(--pt)); font-weight: 700; color: var(--navy);
          line-height: 1; margin-bottom: calc(4 * var(--pt)); }
  .text .card p.evidence { font-size: calc(var(--b) * .66 * var(--pt)); color: var(--muted);
          border-top: 1px solid var(--rule); margin-top: calc(8 * var(--pt)); padding-top: calc(6 * var(--pt)); }
  .tg { display: inline-block; padding: 0 .35em; font-weight: 700; font-size: .92em; }
  .tg.yes { background: #04084A; color: #fff; }
  .tg.partly { background: #D9DBE8; color: #04084A; }
  .tg.no { background: #E3E3E3; color: #383838; }
  .tnote { display: block; color: var(--muted); font-size: .8em; font-weight: 400; margin-top: calc(2 * var(--pt)); }
  th.hl, td.hl { background: #ECEDF4; padding-left: calc(6 * var(--pt)); }
  .title .text { top: 42%; height: auto; justify-content: flex-start; }
  .title .text p { font-size: calc(32 * var(--pt)); line-height: 1.2; }
  .title .text p.strong { font-weight: 700; }
  .section, .photo-section { background: var(--navy); color: #fff; }
  .section h1, .photo-section h1 { font-size: calc(var(--s) * var(--pt)); }
  .section .marking, .section .num, .photo-section .marking, .photo-section .num { color: #c9cbe0; }
  .photo-section { background: var(--navy) url("{{photo}}") center / cover; }
  .photo-section::before { content: ""; position: absolute; inset: 0; background: rgb(4 8 74 / 40%); }
  body.present { overflow: hidden; background: #000; }
  body.present .deck { height: 100%; justify-content: center; padding: 0; }
  body.present .slide { display: none; width: min(100vw, calc(100vh * 16 / 9)); }
  body.present .slide.current { display: block; }
  .hint { color: #aaa; font-size: 14px; text-align: center; }
  body.present .hint { display: none; }
  /* Speaker notes: hidden until N is pressed. Then under each slide, over the foot of the
     screen when presenting, and as a page after each slide when printed. */
  .notes { display: none; width: min(100%, 1280px); margin-top: -12px; color: #e6e6e6;
           font-size: 16px; line-height: 1.5; }
  body.notes-on .notes { display: block; }
  body.present .notes, body.present.notes-on .notes { display: none; }
  body.present.notes-on .notes.current { display: block; position: fixed; left: 0; right: 0; bottom: 0;
           width: auto; margin: 0; max-height: 35vh; overflow: auto; padding: 16px 24px;
           background: rgb(0 0 0 / 88%); color: #fff; z-index: 2; }
  @media print { @page { size: 10in 5.625in; margin: 0; }
    body, .deck { background: none; padding: 0; gap: 0; }
    .slide { width: 10in; break-after: page; } .hint { display: none; }
    body.notes-on .notes { width: 10in; height: 5.625in; margin: 0; padding: .6in; color: #0B0C0C;
           background: #fff; font-size: 14pt; break-after: page; } }
</style>
</head>
<body>
<main class="deck">
<p class="hint">Press P to present, N for speaker notes, arrow keys to move, Escape to stop.</p>
{{slides}}
</main>
<script>
  const slides = [...document.querySelectorAll('.slide')];
  const notes = [...document.querySelectorAll('.notes')];
  let i = 0;
  const show = n => { i = Math.max(0, Math.min(slides.length - 1, n));
    slides.forEach((s, k) => s.classList.toggle('current', k === i));
    notes.forEach(a => a.classList.toggle('current', +a.dataset.slide === i)); };
  document.addEventListener('keydown', e => {
    const on = document.body.classList.contains('present');
    if (e.key === 'p' || e.key === 'P') { document.body.classList.add('present'); show(i); }
    else if (e.key === 'n' || e.key === 'N') document.body.classList.toggle('notes-on');
    else if (e.key === 'Escape') document.body.classList.remove('present');
    else if (on && ['ArrowRight', 'PageDown', ' '].includes(e.key)) { e.preventDefault(); show(i + 1); }
    else if (on && ['ArrowLeft', 'PageUp'].includes(e.key)) show(i - 1);
  });
</script>
</body>
</html>
"""


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("outline")
    ap.add_argument("--out")
    ap.add_argument("--format", default="pptx,html")
    a = ap.parse_args()
    if a.outline.endswith(".json"):
        with open(a.outline) as f:
            outline = json.load(f)
    else:
        from outline import OutlineError, parse

        try:
            outline = parse(a.outline)
        except OutlineError as e:
            sys.exit(f"{a.outline}: {e}")
    name = outline["name"]
    out = os.path.abspath(a.out or os.path.join(os.getcwd(), "decks", name))
    os.makedirs(out, exist_ok=True)
    slides = expand(outline)
    for w in check(slides, deck_sizes(outline)):
        print("WARNING", w)
    formats = a.format.split(",")
    try:
        import pptx  # noqa: F401
    except ImportError:
        if "html" not in formats:
            sys.exit("PowerPoint needs python-pptx: python3 -m pip install --user python-pptx")
        print(
            "WARNING python-pptx not installed, so no PowerPoint file. Building HTML only; "
            "run scripts/check.py to set up PowerPoint."
        )
        formats = [f for f in formats if f != "pptx"]
    if "pptx" in formats:
        pptx = os.path.join(out, name + ".pptx")
        build_pptx(slides, pptx, deck_sizes(outline), os.path.dirname(os.path.abspath(a.outline)))
        print("pptx", pptx)
        if find_cli():
            sheet = render(pptx, os.path.join(out, "render"))
            print("render", sheet or os.path.join(out, "render"))
        else:
            print("No previews: deckcraft-cli is not installed. Check the layout in the HTML deck.")
    if "html" in formats:
        html = os.path.join(out, name + ".html")
        build_html(slides, outline, html, os.path.dirname(os.path.abspath(a.outline)))
        print("html", html)


if __name__ == "__main__":
    main()
