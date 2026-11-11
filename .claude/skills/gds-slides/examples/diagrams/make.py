"""Diagrams for examples/layouts.json. Run: python3 examples/diagrams/make.py"""

import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "..", "scripts"))
from diagram import area, box, line, strong, svg, text, write  # noqa: E402


def build():
    """One outline, two formats: for the right half of a split slide."""
    g = strong(120, 10, 160, 56, "Outline", "one JSON file")
    g += line(200, 66, 200, 120) + text(208, 98, "build.py", 12, 400, anchor="start")
    g += area(20, 130, 360, 160, "Built every time, never edited")
    g += box(45, 185, 140, 60, "PowerPoint", "for sharing") + box(
        215, 185, 140, 60, "HTML", "for presenting"
    )
    return svg(400, 300, g, "One outline is built into a PowerPoint file and an HTML deck")


def workflow():
    """The five steps, full width."""
    steps = [
        ("Brief", "the one thing"),
        ("Headings", "agreed first"),
        ("Outline", "JSON and notes"),
        ("Build", "both formats"),
        ("Look", "every slide"),
    ]
    g = ""
    for i, (label, sub) in enumerate(steps):
        x = 10 + i * 156
        g += (strong if label == "Outline" else box)(x, 20, 124, 60, label, sub)
        if i < len(steps) - 1:
            g += line(x + 124, 50, x + 156, 50)
    g += line(696, 80, 696, 120, head=False, dash="5 4") + line(
        696, 120, 384, 120, head=False, dash="5 4"
    )
    g += line(384, 120, 384, 84, dash="5 4") + text(540, 140, "Fix the outline and rebuild", 12)
    return svg(
        780,
        150,
        g,
        "Brief, headings, outline, build and look, with a loop from look back to the outline",
    )


write(os.path.join(HERE, "build.svg"), build())
write(os.path.join(HERE, "workflow.svg"), workflow())
