"""Edit an existing .pptx in place, keeping everything you don't name exactly as it was.

    /usr/bin/python3 edit.py show    DECK [--slide N]
    /usr/bin/python3 edit.py replace DECK OLD NEW [--slide N ...] [--dry-run]
    /usr/bin/python3 edit.py notes   DECK N TEXT [--append]
    /usr/bin/python3 edit.py hide    DECK N [--show]
    /usr/bin/python3 edit.py move    DECK FROM TO
    /usr/bin/python3 edit.py compare BEFORE AFTER

For decks that people have changed in PowerPoint, or that this skill didn't build. Rebuilding
from the outline would throw those changes away; these commands change only what they name.
Slides are numbered from 1, in presentation order.

replace works on text runs, so the replaced text keeps the font, size, colour and links of the
run where the match starts. It looks in text boxes, placeholders, tables and groups, not in
charts, SmartArt or pictures.

Every command that writes first copies the deck to a backup (its path is printed) and refuses
to run while PowerPoint has the file open. compare checks one deck against another slide by
slide: the XML, the pictures and media, and the notes. Run it against the backup after an edit.
"""
import argparse
import datetime
import difflib
import hashlib
import os
import re
import shutil
import sys
import tempfile

try:
    from lxml import etree
    from pptx import Presentation
except ImportError:
    sys.exit(f"python-pptx is missing. Run: {sys.executable} -m pip install --user python-pptx")

BACKUPS = os.path.join(tempfile.gettempdir(), "gds-slides-backups")


def open_check(path):
    """PowerPoint for Mac and Windows writes ~$<name> beside a file it has open."""
    lock = os.path.join(os.path.dirname(os.path.abspath(path)), "~$" + os.path.basename(path))
    if os.path.exists(lock):
        sys.exit(f"{os.path.basename(path)} looks open in PowerPoint ({lock} exists). "
                 "Close it there and run this again. Editing an open deck causes a sync conflict.")


def backup(path):
    os.makedirs(BACKUPS, exist_ok=True)
    stamp = datetime.datetime.now().strftime("%Y%m%d-%H%M%S-%f")
    name, ext = os.path.splitext(os.path.basename(path))
    dest = os.path.join(BACKUPS, f"{name}-{stamp}{ext}")
    shutil.copy2(path, dest)
    print(f"backup: {dest}")
    return dest


def save(prs, path):
    """Save to a temporary file, then copy over the deck so a failed save leaves it whole."""
    fd, tmp = tempfile.mkstemp(suffix=".pptx")
    os.close(fd)
    try:
        prs.save(tmp)
        shutil.copyfile(tmp, path)
    finally:
        os.remove(tmp)
    print(f"saved: {path}")


def slide_at(prs, n):
    if not 1 <= n <= len(prs.slides):
        sys.exit(f"There is no slide {n}. The deck has {len(prs.slides)}.")
    return prs.slides[n - 1]


def frames(shapes):
    """Every text frame on a slide, including those in tables and groups."""
    for sh in shapes:
        if sh.shape_type == 6:  # group
            yield from frames(sh.shapes)
        if getattr(sh, "has_text_frame", False) and sh.has_text_frame:
            yield sh, sh.text_frame
        if getattr(sh, "has_table", False) and sh.has_table:
            for row in sh.table.rows:
                for cell in row.cells:
                    yield sh, cell.text_frame


def replace_in_paragraph(para, old, new):
    """Replace every match in a paragraph. A match split across runs goes into its first run."""
    runs = list(para.runs)
    text = "".join(r.text for r in runs)
    if old not in text:
        return 0
    starts, pos = [], 0
    for r in runs:
        starts.append(pos)
        pos += len(r.text)
    count, out, cursor = 0, [r.text for r in runs], 0
    # Work from the end so earlier positions stay valid.
    matches = []
    while True:
        i = text.find(old, cursor)
        if i < 0:
            break
        matches.append(i)
        cursor = i + len(old)
    for i in reversed(matches):
        end = i + len(old)
        # The run holding the match's first character keeps the replacement and its formatting.
        first = next(k for k in range(len(runs)) if starts[k] <= i < starts[k] + len(runs[k].text))
        for k in range(len(runs)):
            a, b = starts[k], starts[k] + len(runs[k].text)
            lo, hi = max(a, i), min(b, end)
            if lo >= hi:
                continue
            # Matches are handled from the end, so a later match only changed characters to the
            # right of this one and these offsets into the original run still hold.
            s = out[k]
            out[k] = s[:lo - a] + (new if k == first else "") + s[hi - a:]
        count += 1
    # Indexing rather than zip(strict=...), which Python 3.9 on a GDS Mac doesn't have.
    for k, r in enumerate(runs):
        if r.text != out[k]:
            r.text = out[k]
    return count


def cmd_show(a):
    prs = Presentation(a.deck)
    for n, s in enumerate(prs.slides, 1):
        if a.slide and n != a.slide:
            continue
        hidden = " hidden" if s._element.get("show") == "0" else ""
        print(f"--- slide {n}{hidden} [{s.slide_layout.name}]")
        for sh, tf in frames(s.shapes):
            t = tf.text.strip()
            if t:
                print(f"  {sh.name}: {t[:300]}".replace("\n", " / "))
        if s.has_notes_slide and s.notes_slide.notes_text_frame.text.strip():
            print("  NOTES: " + s.notes_slide.notes_text_frame.text.strip()[:300].replace("\n", " / "))


def cmd_replace(a):
    if not a.dry_run:
        open_check(a.deck)
    prs = Presentation(a.deck)
    total = 0
    for n, s in enumerate(prs.slides, 1):
        if a.slide and n not in a.slide:
            continue
        count = sum(replace_in_paragraph(p, a.old, a.new) for _, tf in frames(s.shapes) for p in tf.paragraphs)
        if count:
            print(f"slide {n}: {count} replaced")
        total += count
    if not total:
        sys.exit(f"Not found: {a.old!r}. Check the text with: edit.py show {a.deck}")
    if a.dry_run:
        print(f"{total} would be replaced. Nothing saved.")
        return
    backup(a.deck)
    save(prs, a.deck)


def cmd_notes(a):
    open_check(a.deck)
    prs = Presentation(a.deck)
    tf = slide_at(prs, a.n).notes_slide.notes_text_frame
    if a.append and tf.text.strip():
        tf.add_paragraph().text = a.text
    else:
        tf.text = a.text
    backup(a.deck)
    save(prs, a.deck)


def cmd_hide(a):
    open_check(a.deck)
    prs = Presentation(a.deck)
    el = slide_at(prs, a.n)._element
    if a.show:
        el.attrib.pop("show", None)
    else:
        el.set("show", "0")
    backup(a.deck)
    save(prs, a.deck)


def cmd_move(a):
    open_check(a.deck)
    prs = Presentation(a.deck)
    slide_at(prs, a.frm)  # exits if either position is out of range
    slide_at(prs, a.to)
    lst = prs.slides._sldIdLst
    ids = list(lst)
    el = ids[a.frm - 1]
    lst.remove(el)
    lst.insert(a.to - 1, el)
    backup(a.deck)
    save(prs, a.deck)


def fingerprint(path):
    """Slides keyed by PowerPoint's slide id, which survives saves and moves, in deck order."""
    out = {}
    for n, s in enumerate(Presentation(path).slides, 1):
        el = s._element
        hidden = el.get("show") == "0"
        el = etree.fromstring(etree.tostring(el))
        el.attrib.pop("show", None)
        media = sorted((r.reltype.rsplit("/", 1)[-1], hashlib.md5(r.target_part.blob).hexdigest())
                       for r in s.part.rels.values()
                       if not r.is_external and not r.reltype.endswith("/notesSlide"))
        notes = etree.tostring(s.notes_slide._element) if s.has_notes_slide else b""
        out[s.slide_id] = (etree.tostring(el), media, notes, n, hidden)
    return out


def texts(xml):
    return [t.decode("utf-8", "replace") for t in re.findall(rb"<a:t>([^<]*)</a:t>", xml)]


def cmd_compare(a):
    A, B = fingerprint(a.before), fingerprint(a.after)
    for sid in A.keys() - B.keys():
        print(f"slide {A[sid][3]}: removed")
    for sid in B.keys() - A.keys():
        print(f"slide {B[sid][3]}: added")
    changed = len(A.keys() ^ B.keys())
    for sid in sorted(A.keys() & B.keys(), key=lambda k: B[k][3]):
        x, y = A[sid], B[sid]
        parts = [name for name, i in (("slide", 0), ("pictures and media", 1), ("notes", 2)) if x[i] != y[i]]
        if x[3] != y[3]:
            parts.append(f"moved from {x[3]}")
        if x[4] != y[4]:
            parts.append("now hidden" if y[4] else "no longer hidden")
        if not parts:
            continue
        changed += 1
        n = y[3]
        print(f"slide {n}: {', '.join(parts)}")
        for i in (0, 2):
            if x[i] == y[i]:
                continue
            for line in difflib.unified_diff(texts(x[i]), texts(y[i]), lineterm="", n=0):
                if line[:1] in "+-" and not line.startswith(("+++", "---")):
                    print("    " + line[:200])
            if i == 0 and re.sub(rb"<a:t>[^<]*</a:t>", b"", x[i]) != re.sub(rb"<a:t>[^<]*</a:t>", b"", y[i]):
                print("    (more than text changed on this slide)")
    print(f"{changed} of {len(B)} slides changed." if changed else "No slides changed.")


def main():
    p = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    sub = p.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("show")
    s.add_argument("deck")
    s.add_argument("--slide", type=int)
    s = sub.add_parser("replace")
    s.add_argument("deck")
    s.add_argument("old")
    s.add_argument("new")
    s.add_argument("--slide", type=int, action="append")
    s.add_argument("--dry-run", action="store_true")
    s = sub.add_parser("notes")
    s.add_argument("deck")
    s.add_argument("n", type=int)
    s.add_argument("text")
    s.add_argument("--append", action="store_true")
    s = sub.add_parser("hide")
    s.add_argument("deck")
    s.add_argument("n", type=int)
    s.add_argument("--show", action="store_true")
    s = sub.add_parser("move")
    s.add_argument("deck")
    s.add_argument("frm", type=int)
    s.add_argument("to", type=int)
    s = sub.add_parser("compare")
    s.add_argument("before")
    s.add_argument("after")
    a = p.parse_args()
    if a.cmd != "compare" and not os.path.exists(a.deck):
        sys.exit(f"No such file: {a.deck}")
    globals()["cmd_" + a.cmd](a)


if __name__ == "__main__":
    main()
