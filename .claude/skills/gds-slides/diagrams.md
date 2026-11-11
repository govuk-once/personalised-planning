# Diagrams

Draw a diagram when the point of a slide is a model, a flow or a relationship, and words would make the audience build the picture in their heads. Don't draw one to decorate a slide.

## How

Write a short Python script in the deck folder, `diagrams/make.py`, that imports `scripts/diagram.py` and writes one SVG per diagram into `diagrams/`. Point the slide's `diagram` field at the SVG and give it `alt` text. `examples/diagrams/make.py` is a worked example, used by `examples/layouts.md` and `examples/using-gds-slides.md`.

```bash
python3 <folder>/diagrams/make.py
```

Keep the script with the deck, so a diagram is changed by editing the script and rebuilding, like the outline.

## Style

- **One visual language per deck.** When several diagrams show variants of one model, draw the same elements in the same places and change only what differs between them. The audience then sees the difference at a glance.
- **Navy for the subject.** Use `strong()` for the one thing the diagram is about. Everything else is a white `box()` with a black outline.
- **Line style carries meaning, with a label.** Solid for a live link, dashed for a planned, documented or optional one, no line for no link. Label every line that isn't obvious, because a dash alone is a colour-free code the audience must decode.
- **Boundaries are dashed areas.** Use `area()` for who owns or runs something: a team, an account, a sandbox.
- **Few words.** A box label is two or three words, with an optional short second line. Explanations go on the slide or in the notes.

## Sizes

The SVG is scaled to fit its space, so its width in units sets how big the text comes out. Draw at about 400 units wide for the right half of a `split` slide, and 700 to 800 for a full-width `diagram` slide. At those widths the default 13-unit labels read close to the deck's body size. A wider drawing shrinks its text: three panels side by side at 1240 units is the practical limit. Leave 10 to 20 units of margin so nothing touches the edge, and check that labels to the side of a line stay inside the width: Quick Look and browsers both clip at the viewBox.
