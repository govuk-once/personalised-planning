---
name: gds-slides
description: GDS slide decks in the GDS 2025 template, as PowerPoint, HTML or both. Use for any presentation, pitch, deck or slides for GDS, before the generic pptx skill.
---

# GDS slides

Builds a deck from a Markdown **outline** using the GDS 2025 template in this folder. One outline produces a PowerPoint file (built with python-pptx) and a self-contained HTML deck. The outline is the master copy. To change a deck, edit the outline and rebuild, until someone changes the PowerPoint file by hand. From then on the PowerPoint file is the master copy: edit it in place, as below, because a rebuild would throw their changes away.

Read [writing.md](writing.md) before drafting, [slides.md](slides.md) before writing the outline, and [diagrams.md](diagrams.md) before drawing a diagram.

`<skill>` below is this skill's base directory. Use a Python 3 that has python-pptx and Pillow: on a GDS Mac that is usually `/usr/bin/python3`. If a build fails on a missing tool, run `python3 <skill>/scripts/check.py` and follow what it says.

## Steps

1. **Brief.** Establish the audience, the purpose, and the one thing the room should leave with. Draw the content from the user's material and the project's documents. Note any source that is marked draft. Ask whether they have photos or screenshots to include, and see "Photos and screenshots" in [slides.md](slides.md). Done when you can state the one thing in a sentence.
2. **Headings.** Draft the deck as a list of slide types and headings only, and show it to the user. Done when the user has approved the list, or has already given you the structure. Changing the story costs nothing at this stage and a rebuild later.
3. **Outline.** Write the full outline as `<name>.md` in the output folder, in the format [slides.md](slides.md) describes, following the examples in `examples/`. The user can read and edit it, so show it to them when they ask to see the deck's content. The output folder is `decks/<name>/` in the working directory, unless the user or the project's CLAUDE.md names another. Put detail and sources in `notes`. If the deck will be read on screens rather than presented, set `Density: discuss` and use the parts in the "Decks for discussion" section of [slides.md](slides.md).
4. **Build.**

   ```bash
   python3 <skill>/scripts/build.py <folder>/<name>.md --out <folder>
   ```

   Add `--format html` or `--format pptx` to build one format only. Done when the script has printed a path for each format and no warnings. A warning means cut words in the outline and rebuild.
5. **Look.** If DeckCraft is installed, the build also writes previews of the PowerPoint slides: read `render/contact.png`. Otherwise, or for HTML, open the deck in a browser and step through it (P presents, N shows speaker notes, arrow keys move). Check every slide for text running into the GDS tag or the slide edge, headings over two lines, and empty or leftover template text. Fix the outline and rebuild until every slide passes. DeckCraft splits the master's OFFICIAL marking across two lines in its renders, so ignore that.
6. **Hand over.** Give the user both files, and say which slides, if any, you could not get to pass.

## Editing a deck in place

Use this when the user has changed a deck in PowerPoint, or wants changes to a deck this skill didn't build. That includes a deck in a OneDrive or SharePoint folder synced to their Mac: edit the file there and OneDrive syncs it back. Without a synced folder, the user saves a copy from PowerPoint, you edit that, and they upload it.

1. **Close it.** Ask the user to close the deck in PowerPoint. `edit.py` refuses to write while PowerPoint has the file open, because a file changed on disk while it is open ends in a sync conflict.
2. **Read it.** `python3 <skill>/scripts/edit.py show <deck>` lists each slide's text and speaker notes, numbered in presentation order.
3. **Edit.** `edit.py replace`, `notes`, `hide` and `move` change only what they name. `replace` keeps the formatting of the text it replaces. Run it with `--dry-run` first, and narrow it with `--slide N` when the text could match elsewhere. Each command that writes prints the path of a backup.
4. **Check.** `edit.py compare <backup> <deck>`. Done when it lists only the changes you meant. Then tell the user they can reopen the deck.

For anything `edit.py` doesn't cover, such as new shapes or a changed picture, write a short python-pptx script that touches only what it must, run it on a copy, and check it with `compare` before replacing the deck. New slides are better built with `build.py` into a separate file for the user to paste in, so they pick up the template.

## Rules

- Build new PowerPoint files only through `scripts/build.py`, and change existing ones in place as above. After an in-place edit the outline is out of date: say so, and don't rebuild from it unless the user wants their hand edits discarded. Keep `template.pptx` byte-for-byte as supplied. Make template changes in PowerPoint for the web and replace the file whole.
- Without python-pptx, the build warns and makes the HTML deck only. Tell the user there is no PowerPoint file and why.
- Without `deckcraft-cli` (on the `PATH`, in `~/.local/bin`, or named by `DECKCRAFT_CLI`), there are no previews. Check the layout in the HTML deck, which uses the same positions and sizes.
- The template prints OFFICIAL on every slide. If the material is above OFFICIAL, say so and stop.
- `examples/using-gds-slides.html` is the built example, kept so people can see the output before installing. After changing `examples/using-gds-slides.md`, its diagrams, `scripts/build.py` or the template, rebuild it in the same change: `python3 <skill>/scripts/build.py <skill>/examples/using-gds-slides.md --out <skill>/examples --format html`.

## Known limits

- PowerPoint can wrap text slightly differently from the HTML deck and the previews. Open an important deck in PowerPoint before sending it. A deck built with python-pptx 1.0.2 opened correctly in PowerPoint for the web on 4 November 2026. After upgrading python-pptx, build `examples/layouts.md` and open it there before relying on the new version.
- Diagrams reach PowerPoint as pictures, converted with macOS Quick Look. On other systems, build HTML only.
- The HTML deck copies the template's colours, type sizes, positions and images. It isn't generated from the template file, so a template update reaches it only through `build.py`'s CSS and `MEDIA` map.
