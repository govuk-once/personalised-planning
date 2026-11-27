# Slide types and the outline

An outline is a Markdown file: the deck title, then one `##` heading per slide. A tag in square brackets after the `##` sets the slide type; a heading without a tag is a text slide. `examples/using-gds-slides.md` uses every type at the default sizes and doubles as a short guide to the plugin; `examples/using-gds-slides.html` is that deck built, to open in a browser. `examples/layouts.md` uses tables, a split slide and a diagram at lighter sizes. Run `examples/diagrams/make.py` before building either. `scripts/outline.py` reads the format, and stops with the slide number and what is missing when a slide doesn't parse.

## The deck

```markdown
# How to make GDS slides with Claude
Presenter: Maxwell Riess
Role: Lead Product Manager
Organisation: Government Digital Service
Notes: Speaker notes for the title slide.
```

`Presenter` and `Role` are required. The rest are optional:

- `Organisation` defaults to Government Digital Service.
- `Closing` replaces "Thanks!" on the last slide.
- `Marking` sets the HTML deck's marking line (default OFFICIAL).
- `Sizes` sets the type sizes in points for both formats, for example `Sizes: heading 26, body 16, section 48`.
- `Name` sets the file name. It defaults to the outline's file name.

`Notes` comes last. The title and closing slides are added automatically.

## Slide types

`template.pptx` is the GDS 2025 slide template, exported from Google Slides. Its GDS look lives on twelve **sample slides**, built mostly from loose text boxes, not on named layouts. So each slide in a deck is a copy of a sample slide, made by copying its XML and images, with its text replaced. `SAMPLES` in `scripts/build.py` maps each type to its sample slide.

| Write | Type | Looks like | Use for |
|---|---|---|---|
| `## Heading` then a sentence, or a `-` list | `text` | Off-white, bold 36pt heading, 24pt body, GDS tag bottom left | Almost everything |
| `## [quote]` then `> the quote` and an optional `Source: who said it` line | `quote` | The quote in navy bold beside a navy rule, the source below | A callout, or something a user said, in one or two lines |
| `## [section] Heading` | `section` | Navy, white 72pt bold line | A signpost between parts of the argument |
| `## [photo] Heading` | `photo-section` | Template photo under a navy tint, white 72pt bold line | Text over an image: a signpost with more weight, at most once a deck |

End any slide with a `Notes:` paragraph. Everything after it, up to the next `##`, goes into the PowerPoint file's speaker notes and into the HTML deck, where N shows them.

Body text is 24pt under a 36pt heading, smaller than the template's 40 and 32, and a list of six drops to about 21pt. `LIMITS` in `scripts/build.py` holds the character limits, and the script warns about anything over them.

## Tables and diagrams

Three more types are built from parts rather than from one sample slide. Their heading has one line, and the build warns when it won't fit. In PowerPoint the heading sits in the text slide's box, moved to the top; tables are real, editable tables; diagrams are PNG pictures with alt text, made from the SVG through macOS Quick Look (`qlmanage`), so edit the SVG and rebuild rather than editing the picture.

| Write | Type | Looks like |
|---|---|---|
| `## [table] Heading` then a Markdown table; the first row is the header | `table` | Heading over a table with a navy header rule |
| `## [split] Heading`, labelled blocks (`### Label` then a sentence or a `-` list), then `![alt text](diagrams/file.svg)` | `split` | Labelled text on the left, a diagram on the right |
| `## [diagram] Heading`, an optional lead sentence, then `![alt text](diagrams/file.svg)` | `diagram` | A full-width diagram |

The image path is relative to the outline, and the SVG is inlined into the HTML deck. The alt text describes the diagram for screen readers, so write it as a sentence. The character limits assume the default sizes.

## Decks for discussion

A deck read close up, on a screen, before or during a discussion can carry more words than one presented to a room, as long as they come in small labelled pieces. `Density: discuss` under the title sets 26pt headings, 16pt body and 48pt sections, and loosens the character limits to match. `examples/discuss.md` uses every part below at that density.

| Write | What it adds | Where it works |
|---|---|---|
| `Eyebrow: Why not the existing repos? · 1 of 3` | Optional, and usually left out: a short muted line above the heading, to mark a run of related slides | Any slide except section and quote slides |
| A plain sentence after the heading | A lede: one larger sentence before the cards or table | `cards` and `table` slides (text and diagram slides already have one) |
| `! **Bold lead.** The rest` | A callout: a tinted band with a navy rule. Before any other content it sits under the heading; after it, under the content | Text, `cards`, `table`, `split` and `diagram` slides |
| `## [cards] Heading`, then two to four `### Title` blocks, each a sentence or a short list and an optional `Evidence:` line | Panels across the slide with a navy top rule; evidence sits under a thin rule in muted type | One row of two to four |
| `## [numbered] Heading`, written like `cards` | The same panels with a large navy number in each | Requirements, steps or principles |
| `[yes]`, `[partly]` or `[no]` at the start of a table cell, then an optional note | A scorecard tag: a filled, half-filled or empty circle and the word, with the note under it. Shape and word carry the meaning, not colour | `table` slides |
| `{highlight}` at the end of a table header cell | Shades that column, for the option you are proposing | `table` slides |

In PowerPoint, cards and callouts are ordinary rectangles and text boxes, and tags are text in real table cells, so all of it stays editable. A text slide with a callout is laid out like the composed types, with the heading at the top.

## Not built yet

The template also has an image-beside-text slide (sample 3) and four photo-grid slides (samples 7 to 10). They need a picture swapped in, which the script doesn't do. Leave them out, or build the deck and add those slides by hand in PowerPoint for the web.
