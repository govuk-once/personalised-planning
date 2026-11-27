# Writing GDS slides

The template's own guidance, on its first sample slide: left-aligned Helvetica Neue, 40pt headings, 32pt text, and make a document instead of a deck if you are trying to say too much. Everything below follows from that last line. The register rules at the end apply to every word on a slide and in the notes. Where the project's CLAUDE.md sets its own house style, follow that as well.

## One slide, one point

- **The heading is the point.** Write it as a statement the audience could repeat: "Most users drop out at identity checks", not "Drop-off analysis". A reader who sees only the headings should get the argument.
- **The body supports the heading.** It's one sentence or a short list, never a paragraph. If the body needs two sentences of qualification, the qualification goes in the speaker notes.
- **Detail lives in the notes.** Dates, sources, caveats and the "why" go in `notes`, where the presenter can use them and the slide stays readable from the back of the room.

## Lists

- Three to five items is the working range. Six fits, at a smaller size; more than six is two slides.
- Make items parallel in form: all phrases or all sentences.
- A list of one is a body sentence.
- Not everything is a list. Use a `table` for a comparison or a split of responsibilities, a `split` slide to set the how beside the why, and a diagram when the point is a model or a flow.

## Shape of a deck

- **Lead with the user or citizen problem**, then the offer, then evidence, then the ask.
- **Use section slides as signposts.** The navy `section` slide and the photo `photo-section` slide carry one short line each, and that line should work as a heading for what follows. Two or three per deck is plenty.
- **Use photos for a reason.** A photo earns its place when it shows the thing itself: the people, the place, the screen. Use one or two photo slides in a deck, not one per section.
- **End on the ask.** The last content slide says what you need from the room, and who holds each item.
- **Ten slides is a lot.** A pitch is usually six to eight content slides between the title and closing slides.

## Decks for discussion

A `Density: discuss` deck is read, not presented, so it can say more. The rules above still hold, with these on top:

- **Every slide still makes one point.** The heading is the claim. The lede says why it matters in a sentence. The cards, table or list carry the parts of the argument.
- **Leave the eyebrow out unless it adds structure.** Most slides don't need one. Use it to mark a run of related slides, as in "Why not the existing repos? · 2 of 3", so the run doesn't need a section slide. An eyebrow that only repeats the heading, or labels every slide, is noise.
- **Back claims with evidence lines.** A card's `Evidence:` line holds the specific thing that makes the claim believable: a count, a date, a quotation from the source. "Seven branches have new work since 10 November" beats "it changes often".
- **Be fair to the alternatives.** When comparing options, say what each is good at before saying why it doesn't fit. A scorecard's notes say why, in a few words, not only yes or no.
- **One callout a slide, at most.** Use it for the reassurance or the takeaway the reader must not miss, with the key phrase in bold. If every slide has one, none of them stands out.

## Accessibility

- When text doesn't fit, cut words rather than shrinking type. The build script's character limits assume the template's sizes.
- The defaults, 30pt headings and 18pt body, leave space around the text. To change them, set the outline's `sizes` for the whole deck. Never shrink one slide to make it fit.
- Make every heading unique, so slide titles work for navigation and screen readers.
- Never use colour as the only signal of meaning. The template's colours are for structure, not emphasis.

## Classification

The template's master prints OFFICIAL on every slide. Decks above OFFICIAL need a different master, which this skill doesn't build. If the material is OFFICIAL-SENSITIVE, say so and stop.

## Register

Plain, direct and professional, for a senior civil service audience. Plain English, short sentences, active voice, sentence case in every heading. Name real uncertainty plainly rather than hedging.

Leave out the markers of machine-written text:

- Em dashes
- Emoji
- Sycophantic or filler openers and transitions: "great question", "it is worth noting", "moving forward", "furthermore", "in summary"
- Vague intensifiers and hedges: "very", "quite", "significantly", "it could be argued"
- Capitals on concepts that are not proper nouns
- "Delve", "foster", "leverage" as a verb, "robust", "seamless", "transformative", "pivotal", "streamline", and "navigate" used metaphorically

Where the presenter has a distinctive phrase that carries an idea well, keep it. Don't flatten it into generic prose.
