"""Diagrams for examples/layouts.md and examples/using-gds-slides.md. Run: python3 examples/diagrams/make.py"""

import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "..", "scripts"))
from diagram import NAVY, area, box, line, strong, svg, text, write  # noqa: E402


def renewal():
    """A made-up service's three steps, for the right half of a split slide."""
    g = box(110, 10, 180, 60, "Apply", "online, about 5 minutes")
    g += line(200, 70, 200, 108)
    g += area(20, 100, 360, 120, "Done by the service")
    g += strong(110, 135, 180, 60, "Check", "against records")
    g += line(200, 220, 200, 238) + box(110, 240, 180, 50, "Permit", "sent the same day")
    return svg(400, 300, g, "Apply online, the service checks against its records, and the permit is sent the same day")


def routes():
    """The made-up service's old and new routes to a permit, full width. Dashed for the old route."""
    g = text(10, 40, "Before", 14, 700, anchor="start") + text(10, 155, "Now", 14, 700, anchor="start")
    for i, (label, sub) in enumerate([("Paper form", "filled in by hand"), ("Post", "up to a week"), ("Manual check", "two weeks")]):
        x = 90 + i * 170
        g += box(x, 5, 140, 60, label, sub, dash="5 4")
        if i < 2:
            g += line(x + 140, 35, x + 168, 35, dash="5 4")
    g += line(570, 35, 598, 78, dash="5 4")
    g += box(90, 120, 140, 60, "Online form", "about 5 minutes")
    g += line(230, 150, 258, 150) + box(260, 120, 310, 60, "Automatic check", "against the service's records")
    g += line(570, 150, 598, 108)
    g += strong(600, 60, 160, 64, "Permit", "same result")
    return svg(
        780,
        190,
        g,
        "Before: paper form, post and a manual check. Now: an online form and an automatic check. Both end with the same permit",
    )


def workflow():
    """The five steps of making a deck, full width, large type."""
    steps = [
        ("Brief", "the one thing"),
        ("Headings", "agreed first"),
        ("Outline", "slides and notes"),
        ("Build", "both formats"),
        ("Look", "every slide"),
    ]
    g = ""
    for i, (label, sub) in enumerate(steps):
        x = 10 + i * 166
        if label == "Outline":
            g += box(x, 20, 136, 76, label, sub, NAVY, "#fff", NAVY, size=18)
        else:
            g += box(x, 20, 136, 76, label, sub, size=18)
        if i < len(steps) - 1:
            g += line(x + 136, 58, x + 164, 58)
    g += line(742, 96, 742, 140, head=False, dash="5 4") + line(742, 140, 410, 140, head=False, dash="5 4")
    g += line(410, 140, 410, 100, dash="5 4") + text(576, 160, "Fix the outline and rebuild", 14)
    return svg(
        820,
        175,
        g,
        "Brief, headings, outline, build and look, with a loop from look back to the outline",
    )


def formats():
    """One outline, two versions of the deck, and what each is for: full width, large type."""
    g = box(20, 80, 170, 80, "Outline", "one Markdown file", NAVY, "#fff", NAVY, size=18)
    g += line(190, 120, 278, 120) + box(280, 95, 150, 50, "build.py", "one command", size=16)
    g += line(430, 120, 508, 78) + line(430, 120, 508, 178)
    g += area(490, 8, 262, 224, "decks/<name>/")
    g += box(510, 40, 225, 76, "PowerPoint", "edit and collaborate", size=18)
    g += box(510, 140, 225, 76, "HTML", "share in one file", size=18)
    g += line(622, 232, 622, 252, head=False, dash="5 4") + line(622, 252, 105, 252, head=False, dash="5 4")
    g += line(105, 252, 105, 164, dash="5 4") + text(365, 246, "Change the outline, rebuild both", 14)
    return svg(
        760,
        270,
        g,
        "An outline is built by build.py into a PowerPoint file, for editing and collaborating, "
        "and an HTML file, for sharing. To change the deck, change the outline and rebuild both",
    )


write(os.path.join(HERE, "renewal.svg"), renewal())
write(os.path.join(HERE, "workflow.svg"), workflow())
write(os.path.join(HERE, "routes.svg"), routes())
write(os.path.join(HERE, "formats.svg"), formats())
