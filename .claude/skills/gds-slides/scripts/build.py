"""Build a GDS deck from an outline: PowerPoint with python-pptx, HTML directly.

    /usr/bin/python3 build.py OUTLINE.json [--out DIR] [--format pptx,html]

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
SAMPLES = {"title": 1, "text": 2, "section": 4, "photo-section": 5, "closing": 11}
# Slide types built from parts rather than from one sample slide. Diagrams need macOS Quick Look for PowerPoint.
COMPOSED = ("table", "split", "diagram")
# Template media used by the HTML deck
MEDIA = {
    "lockup": "ppt/media/image1.png",
    "tag": "ppt/media/image2.png",
    "photo": "ppt/media/image6.jpg",
}
# Characters. Over these, the text does not fit the template's type sizes.
LIMITS = {"heading": 65, "body": 170, "bullet": 55, "bullets": 6, "section": 45}
# Points, on a 720pt-wide slide. Template asks for 40 and 32; 28 is the most body text fits.
SIZE = {"heading": 40, "body": 28, "dense": 24, "title": 32}


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


def check(slides):
    warn = []
    for n, (kind, head, body, *_) in enumerate(slides, 1):
        if kind in COMPOSED:
            continue
        if kind not in SAMPLES:
            sys.exit(
                f"Slide {n}: unknown type {kind!r}. Use one of {sorted(SAMPLES) + list(COMPOSED)}."
            )
        if kind in ("section", "photo-section"):
            if len(head or "") > LIMITS["section"]:
                warn.append(
                    f"slide {n}: section heading {len(head)} chars, limit {LIMITS['section']}"
                )
        elif kind == "text":
            if len(head or "") > LIMITS["heading"]:
                warn.append(f"slide {n}: heading {len(head)} chars, limit {LIMITS['heading']}")
            if len(body) > LIMITS["bullets"]:
                warn.append(f"slide {n}: {len(body)} bullets, limit {LIMITS['bullets']}")
            for b in body if len(body) > 1 else []:
                if len(b) > LIMITS["bullet"]:
                    warn.append(
                        f"slide {n}: bullet {len(b)} chars, limit {LIMITS['bullet']}: {b[:30]}..."
                    )
            if len(body) == 1 and len(body[0]) > LIMITS["body"]:
                warn.append(f"slide {n}: body {len(body[0])} chars, limit {LIMITS['body']}")
    return warn


# Slide points (720 x 405) for the composed types in PowerPoint.
FRAME = {"heading": [43, 26, 634, 64], "top": 100, "bottom": 355, "left": 43, "width": 634}
FONT = "Helvetica Neue"
INK, NAVY, RULE = "0B0C0C", "04084A", "CBCBCB"
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
            for tag in ("a:latin", "a:ea", "a:cs", "a:sym"):
                etree.SubElement(rpr, qn(tag), typeface=FONT)
        if para["text"]:
            run = etree.SubElement(p, qn("a:r"))
            run.append(rpr)
            etree.SubElement(run, qn("a:t")).text = para["text"]
        else:
            end = copy.deepcopy(rpr)
            end.tag = qn("a:endParaRPr")
            p.append(end)


def cell_borders(cell, bottom, width):
    """No fill and no lines except a bottom rule, written in the order PowerPoint expects."""
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
    etree.SubElement(tcpr, qn("a:noFill"))


def build_pptx(slides, path, sizes, base):
    from pptx import Presentation
    from pptx.oxml.ns import qn
    from pptx.util import Pt

    prs = Presentation(TEMPLATE)
    samples = len(prs.slides)
    src = list(prs.slides)
    art = os.path.join(os.path.dirname(path), "render", "diagrams")

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
        rows = [t["columns"]] + t["rows"]
        cols = len(t["columns"])
        frame = slide.shapes.add_table(
            len(rows), cols, Pt(FRAME["left"]), Pt(y), Pt(FRAME["width"]), Pt(20 * len(rows))
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
        for r, row in enumerate(rows):
            tbl.rows[r].height = Pt(20)
            for c, value in enumerate(row):
                cell = tbl.cell(r, c)
                paragraphs(
                    cell.text_frame,
                    [{"text": value, "size": sizes["body"] * 0.78, "bold": r == 0 or c == 0}],
                )
                cell_borders(cell, NAVY if r == 0 else RULE, 1.5 if r == 0 else 0.75)

    for kind, *_ in slides:
        copy_slide(prs, src[SAMPLES.get(kind, SAMPLES["text"])])
    drop_slides(prs, samples)

    for slide, (kind, head, body, notes, s) in zip(prs.slides, slides, strict=True):
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
        elif kind == "text":
            size = sizes["body"] * 0.86 if len(body) > 5 else sizes["body"]
            paragraphs(
                box.text_frame,
                [{"text": head, "size": sizes["heading"], "bold": True, "after": 14}]
                + [
                    {"text": t, "size": size, "bullet": len(body) > 1, "indent": 22, "after": 4}
                    for t in body
                ],
            )
        else:
            # Heading in the template's text box, moved to the top; the rest drawn below it.
            paragraphs(box.text_frame, [{"text": head, "size": sizes["heading"], "bold": True}])
            box.left, box.top, box.width, box.height = (Pt(v) for v in FRAME["heading"])
            top, left, width = FRAME["top"], FRAME["left"], FRAME["width"]
            if kind == "table":
                table(slide, s["table"], top)
            elif kind == "split":
                half = (width - 36) / 2
                text_box(slide, s, left, top, half, FRAME["bottom"] - top)
                place(slide, s, left + half + 36, top, half, FRAME["bottom"] - top)
            else:
                lead = 34 if s.get("body") else 0
                text_box(slide, s, left, top, width, lead)
                place(slide, s, left, top + lead, width, FRAME["bottom"] - top - lead)
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
    head = "".join(f"<th>{esc(c)}</th>" for c in t["columns"])
    rows = "".join("<tr>" + "".join(f"<td>{esc(c)}</td>" for c in r) + "</tr>" for r in t["rows"])
    return f"<table><thead><tr>{head}</tr></thead><tbody>{rows}</tbody></table>"


def deck_sizes(outline):
    """Type sizes in points, with the outline's optional `sizes` over the template's."""
    return {
        "heading": SIZE["heading"],
        "body": SIZE["body"],
        "section": 72,
        **outline.get("sizes", {}),
    }


def build_html(slides, outline, path, base):
    z = zipfile.ZipFile(TEMPLATE)
    uri = {
        k: f"data:image/{v.rsplit('.', 1)[1].replace('jpg', 'jpeg')};base64,"
        + base64.b64encode(z.read(v)).decode()
        for k, v in MEDIA.items()
    }
    marking = outline.get("marking", "OFFICIAL")
    lockup = f'<img class="lockup" src="{uri["lockup"]}" alt="Government Digital Service, Department for Science, Innovation and Technology">'
    out = []
    for n, (kind, head, body, notes, s) in enumerate(slides, 1):
        foot = f'<img class="tag" src="{uri["tag"]}" alt="GDS"><span class="num">{n}</span>'
        if kind in ("title", "closing"):
            strong = {0} | ({2} if kind == "closing" else set())
            lines = "".join(
                f"<p{' class=strong' if i in strong else ''}>{esc(t) or '&nbsp;'}</p>"
                for i, t in enumerate(body)
            )
            inner, cls, foot = f'{lockup}<div class="text">{lines}</div>', "title", ""
        elif kind in ("section", "photo-section"):
            inner, cls = f'<div class="text"><h1>{esc(head)}</h1></div>', kind
        elif kind == "table":
            inner, cls = (
                f'<div class="text top"><h2>{esc(head)}</h2>{table(s["table"])}</div>',
                "wide",
            )
        elif kind == "split":
            inner = (
                f'<div class="text top"><h2>{esc(head)}</h2><div class="cols">'
                f'<div class="col">{blocks(s)}</div>{svg(base, s)}</div></div>'
            )
            cls = "wide"
        elif kind == "diagram":
            inner, cls = (
                f'<div class="text top"><h2>{esc(head)}</h2>{blocks(s)}{svg(base, s)}</div>',
                "wide",
            )
        else:
            if len(body) > 1:
                text = "<ul>" + "".join(f"<li>{esc(b)}</li>" for b in body) + "</ul>"
            else:
                text = "".join(f"<p>{esc(b)}</p>" for b in body)
            inner = f'<div class="text{" dense" if len(body) > 5 else ""}"><h2>{esc(head)}</h2>{text}</div>'
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
  .slide { position: relative; width: min(100%, 1280px); aspect-ratio: 16 / 9; background: var(--paper);
           color: var(--ink); overflow: hidden; container-type: inline-size; --pt: calc(100cqw / 720); }
  .marking { position: absolute; top: calc(6 * var(--pt)); left: 0; right: 0; text-align: center;
             font-size: calc(7 * var(--pt)); letter-spacing: .04em; color: var(--muted); z-index: 1; }
  .tag { position: absolute; left: 2%; top: 90.7%; width: 9%; z-index: 1; }
  .lockup { position: absolute; left: 5%; top: 9%; width: 43%; }
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
    with open(a.outline) as f:
        outline = json.load(f)
    name = outline["name"]
    out = os.path.abspath(a.out or os.path.join(os.getcwd(), "decks", name))
    os.makedirs(out, exist_ok=True)
    slides = expand(outline)
    for w in check(slides):
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
