"""Read a Markdown outline into the dict build.py works from. slides.md describes the format.

    # Deck title
    Presenter: Name
    Role: Job title
    Notes: Notes for the title slide.

    ## A text slide's heading
    One sentence, or a list:
    - first point
    - second point

    Notes: Speaker notes. Everything after "Notes:" up to the next slide.

    ## [section] A signpost
"""

import os
import re

# Tag in "## [tag] Heading" -> slide type. An untagged heading is a text slide.
TYPES = {
    "section": "section",
    "photo": "photo-section",
    "photo-section": "photo-section",
    "quote": "quote",
    "table": "table",
    "diagram": "diagram",
    "split": "split",
    "cards": "cards",
    "numbered": "cards",
    "image": "image",
    "photos": "photos",
}
# Lines under the title, "Key: value" -> outline field. Notes comes last and runs on.
DECK = {
    "presenter": "name",
    "role": "role",
    "organisation": "org",
    "org": "org",
    "marking": "marking",
    "closing": "closing",
    "name": "name_",
    "sizes": "sizes",
    "density": "density",
    "cover": "cover",
}


class OutlineError(Exception):
    pass


def parse(path):
    with open(path, encoding="utf-8") as f:
        text = f.read()
    sections = []  # [level, heading, lines]
    for line in text.splitlines():
        m = re.match(r"(#{1,2})\s+(.*)$", line)
        if m:
            sections.append([len(m.group(1)), m.group(2).strip(), []])
        elif sections:
            sections[-1][2].append(line)
        elif line.strip():
            raise OutlineError("The outline must start with '# Deck title'.")
    if not sections or sections[0][0] != 1:
        raise OutlineError("The outline must start with '# Deck title'.")

    _, title, lines = sections[0]
    fields, notes = deck(lines)
    who = {k: fields.pop(k) for k in ("name", "role", "org") if k in fields}
    if "role" not in who and "," in who.get("name", ""):
        parts = [p.strip() for p in who["name"].split(",")]
        who.update({k: parts[i] for i, k in enumerate(("name", "role", "org")) if i < len(parts)})
    if "name" not in who or "role" not in who:
        raise OutlineError("Under the title, give 'Presenter:' and 'Role:' lines.")
    outline = {
        "name": fields.pop("name_", None)
        or os.path.splitext(os.path.basename(path))[0],
        "title": title,
        "presenter": who,
        "notes": notes,
        "slides": [],
    }
    if "sizes" in fields:
        outline["sizes"] = {
            k: float(v) for k, v in re.findall(r"(heading|body|section)\s+([\d.]+)", fields.pop("sizes"))
        }
    if fields.get("density", "present").lower() not in ("present", "discuss"):
        raise OutlineError("'Density:' is 'present' (the default) or 'discuss'.")
    if "cover" in fields:
        # "Cover: file.jpg" or "Cover: ![alt](file.jpg)"; the cover photo is decorative either way.
        m = re.match(r"!\[.*\]\((.*)\)$", fields["cover"])
        fields["cover"] = m.group(1) if m else fields["cover"]
    outline.update(fields)
    for n, (level, heading, body) in enumerate(sections[1:], 2):
        if level == 1:
            raise OutlineError(f"Slide {n}: only the deck title uses '#'. Slides use '##'.")
        outline["slides"].append(slide(n, heading, body))
    return outline


def deck(lines):
    fields, notes = {}, None
    for line in lines:
        if notes is not None:
            notes.append(line.strip())
            continue
        m = re.match(r"([A-Za-z]+):\s*(.*)$", line.strip())
        if m and m.group(1).lower() == "notes":
            notes = [m.group(2)]
        elif m and m.group(1).lower() in DECK:
            fields[DECK[m.group(1).lower()]] = m.group(2).strip()
        elif line.strip():
            raise OutlineError(f"Under the title, unrecognised line: {line.strip()!r}")
    return fields, join(notes or [])


def join(lines):
    return " ".join(t for t in (line.strip() for line in lines) if t)


def slide(n, heading, lines):
    m = re.match(r"\[([a-z-]+)\]\s*(.*)$", heading)
    if m and m.group(1) not in TYPES:
        raise OutlineError(f"Slide {n}: unknown tag [{m.group(1)}]. Use one of {sorted(TYPES)}.")
    kind = TYPES[m.group(1)] if m else "text"
    s = {"type": kind}
    if m and m.group(1) == "numbered":
        s["numbered"] = True
    if (m.group(2) if m else heading):
        s["heading"] = m.group(2) if m else heading
    if s.get("heading", "").endswith("{navy}"):
        s["heading"], s["navy"] = s["heading"][: -len("{navy}")].strip(), True

    para, paras, bullets, quote, rows, blocks, notes = [], [], [], [], [], [], None
    seen = False  # any content yet; a callout before it goes at the top of the slide

    def end_para():
        if para:
            target = blocks[-1] if blocks else None
            if target is not None:
                target["text"] = join([target.get("text", "")] + para)
            else:
                paras.append(join(para))
            para.clear()

    for line in lines:
        t = line.strip()
        if notes is not None:
            notes.append(t)
            continue
        if t.lower().startswith("notes:"):
            end_para()
            notes = [t[6:]]
        elif not t:
            end_para()
        elif t.lower().startswith("eyebrow:"):
            s["eyebrow"] = t[8:].strip()
        elif t.startswith("! "):
            end_para()
            s["callout"] = t[2:].strip()
            s["callout_at"] = "bottom" if seen else "top"
        elif t.lower().startswith("evidence:") and blocks:
            end_para()
            blocks[-1]["evidence"] = t[9:].strip()
        elif t.startswith("### "):
            end_para()
            blocks.append({"label": t[4:].strip()})
        elif re.match(r"!\[.*\]\(.*\)$", t):
            end_para()
            alt, src = re.match(r"!\[(.*)\]\((.*)\)$", t).groups()
            s.setdefault("images", []).append({"alt": alt, "src": src})
            if "diagram" not in s:
                s["alt"], s["diagram"] = alt, src
        elif t.startswith(">"):
            quote.append(t[1:].strip())
        elif t.lower().startswith("source:"):
            s["attribution"] = t[7:].strip()
        elif t.startswith("|"):
            cells = [c.strip() for c in t.strip("|").split("|")]
            if not all(re.match(r":?-+:?$", c) for c in cells):
                rows.append(cells)
        elif re.match(r"[-*] ", t):
            end_para()
            item = t[2:].strip()
            if blocks:
                blocks[-1].setdefault("bullets", []).append(item)
            else:
                bullets.append(item)
        else:
            para.append(t)
        if t and not t.lower().startswith(("eyebrow:", "! ", "notes:")):
            seen = True
    end_para()

    if paras:
        s["body"] = " ".join(paras)
    if bullets:
        s["bullets"] = bullets
    if blocks:
        s["blocks"] = blocks
    if notes is not None:
        s["notes"] = join(notes)
    if quote:
        s["quote"] = join(quote)
    if rows:
        s["table"] = {"columns": rows[0], "rows": rows[1:]}

    need = {"quote": "quote", "table": "table", "diagram": "diagram", "split": "diagram"}
    if kind in need and need[kind] not in s:
        what = {"quote": "a '>' quote", "table": "a Markdown table", "diagram": "an image line ![alt](file.svg)"}
        raise OutlineError(f"Slide {n}: a [{kind}] slide needs {what[need[kind]]}.")
    if kind == "image" and "diagram" not in s:
        raise OutlineError(f"Slide {n}: an [image] slide needs an image line ![alt](photo.jpg).")
    if kind == "photos" and len(s.get("images", [])) not in (2, 3):
        raise OutlineError(f"Slide {n}: a [photos] slide needs two or three image lines ![alt](photo.jpg).")
    if kind == "cards" and not 2 <= len(blocks) <= 4:
        raise OutlineError(f"Slide {n}: a [{m.group(1)}] slide needs two to four cards, each a '### Title'.")
    if kind not in ("quote",) and "heading" not in s:
        raise OutlineError(f"Slide {n}: needs a heading after the '##'.")
    return s
