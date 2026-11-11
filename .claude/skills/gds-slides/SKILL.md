---
name: gds-slides
description: GDS slide decks in the GDS 2025 template, as PowerPoint, HTML or both. Use for any presentation, pitch, deck or slides for GDS, before the generic pptx skill.
---

# GDS slides

Builds a deck from a JSON **outline** using the GDS 2025 template in this folder. One outline produces a PowerPoint file (built with python-pptx) and a self-contained HTML deck. The outline is the master copy. To change a deck, edit the outline and rebuild.

Read [writing.md](writing.md) before drafting, [slides.md](slides.md) before writing the outline, and [diagrams.md](diagrams.md) before drawing a diagram.

`<skill>` below is this skill's base directory. Use a Python 3 that has python-pptx and Pillow: on a GDS Mac that is usually `/usr/bin/python3`. If a build fails on a missing tool, run `python3 <skill>/scripts/check.py` and follow what it says.

## Steps

1. **Brief.** Establish the audience, the purpose, and the one thing the room should leave with. Draw the content from the user's material and the project's documents. Note any source that is marked draft. Done when you can state the one thing in a sentence.
2. **Headings.** Draft the deck as a list of slide types and headings only, and show it to the user. Done when the user has approved the list, or has already given you the structure. Changing the story costs nothing at this stage and a rebuild later.
3. **Outline.** Write the full outline as `<name>.json` in the output folder, following the examples in `examples/`. The output folder is `decks/<name>/` in the working directory, unless the user or the project's CLAUDE.md names another. Put detail and sources in `notes`.
4. **Build.**

   ```bash
   python3 <skill>/scripts/build.py <folder>/<name>.json --out <folder>
   ```

   Add `--format html` or `--format pptx` to build one format only. Done when the script has printed a path for each format and no warnings. A warning means cut words in the outline and rebuild.
5. **Look.** If DeckCraft is installed, the build also writes previews of the PowerPoint slides: read `render/contact.png`. Otherwise, or for HTML, open the deck in a browser and step through it (P presents, N shows speaker notes, arrow keys move). Check every slide for text running into the GDS tag or the slide edge, headings over two lines, and empty or leftover template text. Fix the outline and rebuild until every slide passes. DeckCraft splits the master's OFFICIAL marking across two lines in its renders, so ignore that.
6. **Hand over.** Give the user both files, and say which slides, if any, you could not get to pass.

## Rules

- Build PowerPoint files only through `scripts/build.py`. Keep `template.pptx` byte-for-byte as supplied. Make template changes in PowerPoint for the web and replace the file whole.
- Without python-pptx, the build warns and makes the HTML deck only. Tell the user there is no PowerPoint file and why.
- Without `deckcraft-cli` (on the `PATH`, in `~/.local/bin`, or named by `DECKCRAFT_CLI`), there are no previews. Check the layout in the HTML deck, which uses the same positions and sizes.
- The template prints OFFICIAL on every slide. If the material is above OFFICIAL, say so and stop.

## Known limits

- PowerPoint can wrap text slightly differently from the HTML deck and the previews. Open an important deck in PowerPoint before sending it. A deck built with python-pptx 1.0.2 opened correctly in PowerPoint for the web on 4 November 2026. After upgrading python-pptx, build `examples/layouts.json` and open it there before relying on the new version.
- Diagrams reach PowerPoint as pictures, converted with macOS Quick Look. On other systems, build HTML only.
- The HTML deck copies the template's colours, type sizes, positions and images. It isn't generated from the template file, so a template update reaches it only through `build.py`'s CSS and `MEDIA` map.
