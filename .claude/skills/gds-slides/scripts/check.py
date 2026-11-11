"""Check what gds-slides needs, and say what to install. Run: python3 check.py"""

import os
import shutil
import subprocess
import sys

SKILL = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ok = True


def report(good, name, fix):
    global ok
    print(("ok      " if good else "missing ") + name + ("" if good else f"\n        {fix}"))
    ok = ok and good


report(
    sys.version_info >= (3, 8),
    f"Python 3.8 or later (this is {sys.version.split()[0]})",
    "Use /usr/bin/python3 on a Mac, or install a newer Python.",
)
try:
    import PIL  # noqa: F401

    pil = True
except ImportError:
    pil = False
report(
    pil,
    f"Pillow, for {sys.executable}",
    f"{sys.executable} -m pip install --user Pillow   (needed for diagrams in PowerPoint)",
)
cli = next(
    (
        c
        for c in (
            os.environ.get("DECKCRAFT_CLI"),
            shutil.which("deckcraft-cli"),
            os.path.expanduser("~/.local/bin/deckcraft-cli"),
        )
        if c and os.path.exists(c)
    ),
    None,
)
version = ""
if cli:
    try:
        version = subprocess.run(
            [cli, "--version"], capture_output=True, text=True, timeout=20
        ).stdout.strip()
    except Exception:
        pass
try:
    import pptx

    have = f"python-pptx {pptx.__version__}, for {sys.executable}"
except ImportError:
    have = None
report(
    bool(have),
    have or f"python-pptx, for {sys.executable}",
    f"{sys.executable} -m pip install --user python-pptx   (needed for PowerPoint; without it, HTML only)",
)
print(
    ("ok      " if cli else "optional ")
    + (
        f"DeckCraft ({cli}{', ' + version if version else ''}), for previews"
        if cli
        else "DeckCraft, for previews of PowerPoint slides\n        Install deckcraft-cli to ~/.local/bin from "
        "https://github.com/storytold/deckcraft (0.15.0 tested). Without it, Claude checks layout in the HTML deck."
    )
)
report(
    bool(shutil.which("qlmanage")),
    "macOS Quick Look (qlmanage)",
    "Only on macOS. Without it, build decks that have diagrams with --format html.",
)
report(
    os.path.exists(os.path.join(SKILL, "template.pptx")),
    "GDS template (template.pptx)",
    "Reinstall the plugin: the template is missing.",
)
print(
    "\nReady for PowerPoint and HTML."
    if ok
    else "\nHTML decks need only Python. Fix the items above for PowerPoint."
)
