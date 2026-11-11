# Slide types

`template.pptx` is the GDS 2025 slide template, exported from Google Slides. Its GDS look lives on twelve **sample slides**, built mostly from loose text boxes, not on named layouts. So each slide in a deck is a copy of a sample slide, made by copying its XML and images, with its text replaced. `SAMPLES` in `scripts/build.py` maps each type to its sample slide.

| Type | Looks like | Use for | Outline fields |
|---|---|---|---|
| `title` | Off-white, GDS and DSIT lockup top left, title and presenter below | First slide. Added automatically from `title` and `presenter` | none in `slides` |
| `text` | Off-white, bold 40pt heading, 28pt body, GDS tag bottom left | Almost everything | `heading`, then `body` (one sentence) or `bullets` (a list) |
| `section` | Navy, white 72pt bold line | A signpost between parts of the argument | `heading` |
| `photo-section` | Template photo under a navy tint, white 72pt bold line | A signpost with more weight, at most once a deck | `heading` |
| `closing` | As `title`, with "Thanks!" and the presenter | Last slide. Added automatically; `closing` overrides "Thanks!" | none in `slides` |

Every slide type takes an optional `notes`, and the top level takes `notes` for the title slide. Notes go into the PowerPoint file's speaker notes and into the HTML deck, where N shows them.

Body text is 28pt, and 24pt when a list has six items. The template asks for 32pt, which doesn't fit a heading plus body. `LIMITS` in `scripts/build.py` holds the character limits, and the script warns about anything over them.

## Tables and diagrams

Three more types are built from parts rather than from one sample slide. In PowerPoint the heading sits in the text slide's box, moved to the top; tables are real, editable tables; diagrams are PNG pictures with alt text, made from the SVG through macOS Quick Look (`qlmanage`), so edit the SVG and rebuild rather than editing the picture.

| Type | Looks like | Outline fields |
|---|---|---|
| `table` | Heading over a table with a navy header rule | `heading`, `table` (`columns`, `rows`) |
| `split` | Heading, labelled text on the left, a diagram on the right | `heading`, optional `body`, `blocks` (each `label` with `text` or `bullets`), `diagram`, `alt` |
| `diagram` | Heading, optional lead sentence, a full-width diagram | `heading`, optional `body` and `blocks`, `diagram`, `alt` |

`diagram` is the path to an SVG file, relative to the outline, inlined into the deck. `alt` describes it for screen readers. The top-level `sizes` (`heading`, `body`, `section`, in points) sets the type sizes in both formats, for a lighter deck than the template's defaults. The character limits assume the defaults.

## Not built yet

The template also has an image-beside-text slide (sample 3) and four photo-grid slides (samples 7 to 10). They need a picture swapped in, which the script doesn't do. Leave them out, or build the deck and add those slides by hand in PowerPoint for the web.

## The outline

`examples/service-studio-pitch.json` is a complete outline using the template's own types and sizes. `examples/layouts.json` uses tables, a split slide, a diagram and the lighter `sizes`; run `examples/diagrams/make.py` before building it. Top level: `name` (file name, kebab-case), `title`, `presenter` (`name`, `role`, `org`), optional `marking` (the HTML deck's marking line, default OFFICIAL), `notes`, `closing`, and `slides`.
