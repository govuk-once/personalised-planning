# Evaluation pipeline: synthetic users, ground truth, and scoring

## Overview

This is a four-stage pipeline for testing a personalised-plan generator
against a programmatically generated ground-truth set of plans, to evaluate the performance of the plan generator. It runs via the following steps:

1. **Generate synthetic users** (`plans.py`) — read a GOV.UK life-event subgraph (provided by the user, derived from the GOV.UK Knowledge Graph), derive a questionnaire, and produce a batch of synthetic user profiles that cover every answer the questionnaire can give.
2. **Generate ground truth** (`truth.py map` + `truth.py build`) — fetch the matching GOV.UK step by step(s), derive a small mapping from its steps onto the questionnaire, have a human review it, then apply that mapping to every profile to produce an answer key: which steps each synthetic user should
   see.
3. **Generate plans with your app** (`run_app.py`) — call the Personalised Planning agent for each synthetic profile, map the returned tasks back onto spine step numbers, and score the plans against the ground truth.
4. **Evaluate** (`truth.py score`) — compare the app's plans against the answer key and get precision/recall-style scoring, with legally-blocked steps tracked separately from ordinary misses.

Stages 1 and 2 each make a small number of Bedrock calls, reviewed by a
human before being trusted. Stage 3 calls the plan API once per profile and
maps results onto step numbers using the spine — no Bedrock unless you add
`--relevance`. Stage 2's `build` step and stage 4 are pure code — no AI,
no network — so re-running them costs nothing and reruns deterministically.

## Dependency map

```
driving_subgraph.json ──────┐
                             ├──▶ plans.py ──▶ data/driving_model.json ──┬──▶ data/driving_profiles.json
                             │                                          │
        GOV.UK step-by-step  │                                          │
        URL(s) ──────────────┼──▶ truth.py map ──▶ data/mapping.json    │
                             │        (needs driving_model.json)        │
                             │                                          │
                             │        you review data/mapping.json      │
                             │                                          │
                             └────────────────┬─────────────────────────┘
                                               ▼
                                    truth.py build ──▶ data/truth.json
                                    (needs driving_profiles.json,
                                     driving_model.json, mapping.json)

                        data/driving_profiles.json
                                    │
                                    ▼
                      run_app.py (needs data/truth.json)
                                    │
                                    ▼
                            app_plans.json (stdout)
                                    │
                                    ▼
                    truth.py score (needs data/truth.json)
                                    │
                                    ▼
                              scoring report
```

`plans.py` runs first — everything downstream needs `driving_model.json` and
`driving_profiles.json`. `truth.py map` needs `driving_model.json` plus
GOV.UK URL(s); it does not need the subgraph. `truth.py build` needs the
profiles, the model, and the reviewed mapping. `run_app.py` needs the
profiles and `truth.json` — it uses the spine embedded in `truth.json` to
map the API's cited URLs onto step numbers. `truth.py score` is the only
stage that touches the app's output directly.

---

# Part 1 — Generating synthetic user scenarios (`plans.py`)

## What this is for

GOV.UK has 92 pages about learning to drive. Nobody needs all 92. Someone
learning in a car at seventeen and a farmer wanting a tractor licence share
almost nothing.

So the aim is to ask a person a few questions, then show them only the steps
that apply to them. This code works out **what those questions should be** — by
reading the content, rather than by someone guessing.

It then generates **synthetic users**: made-up people, each with a valid set of
answers, so you can check the plans hold up before showing them to anyone real.
And for each one it produces a **review packet**: the specific claims that
person's plan has to satisfy, so a reviewer has something concrete to judge
against.

## How it works

One file, four stages, one command.

**It reads the content.** The whole corpus is flattened into a single prompt
and handed to Claude, which is asked to find every fact about a person that
changes what they have to do — and to ignore anything the guidance treats the
same for everyone. What comes back is a questionnaire: the questions, the
answers, and the rules for when each question should be asked.

**It checks the questionnaire works.** Ordinary code, no AI. It invents
thousands of imaginary people, runs them through, and looks for things that
are broken — a question nobody could ever be asked, an answer that can never
appear, a rule that never does anything. Anything it finds goes back to Claude
to fix, and it checks again. Up to three rounds before it gives up and tells
you.

**It builds the test users.** It walks the questionnaire twenty thousand
times, answering differently each run, and keeps one example of each genuinely
different journey. It also works out each person's age from their answers —
because someone who passed a driving test before 1997 can't be nineteen — and
optionally asks Claude to write them a name and a life.

**It writes the review packets.** For each person, the claims their plan must
satisfy, sorted so the users most likely to break a plan come first.

## Why it's built this way

**The content decides the questions, not us.** Every question has to point at
the page that justifies it. If the guidance doesn't say two people are treated
differently, it isn't a question. This is what keeps the thing honest, and what
lets the same code work for a completely different topic — hand it content
about having a baby and you get questions about due dates and employment
instead, with no changes.

**Anything checkable is checked by code, not by a model.** Claude decides what
the questions are. Ordinary code decides whether they work — whether every
question can be reached, whether the rules contradict each other, whether a
person's age is possible given their other answers. Models are inconsistent at
applying the same five-part rule across hundreds of cases, which is exactly the
workload here.

**Test users are built by code, personas by Claude.** The questionnaire is a
formal object, so valid answer sets can be worked out with guarantees. Asking a
model for "50 diverse users" gets you plausible-looking people clustered around
the obvious cases, sometimes answering questions they'd never be asked, and
missing the rare situations you built the thing to find. Claude writes the part
code can't: a name, a life, a reason they're stuck.

**A reviewer needs something to judge against.** A profile is enough to
*generate* a plan and not enough to *check* one. Asking someone "is this plan
right?" gets an opinion; giving them the specific claims the plan must satisfy
gets a finding.

## What you get, and why it can be trusted

*The figures below are illustrative — one representative run against the 92
driving pages, not a fixed guarantee. Regenerating the model, editing it by hand, or pointing the pipeline at different content will move every count, so treat them as an order-of-magnitude sketch rather than numbers to reconcile against the committed data files.*

Run against the 92 driving pages, one run produced a questionnaire of roughly **twenty questions**, a handful of **derived facts** (things worked out from the answers, like "this person doesn't need a theory test"), a few **rules** hiding answers that don't apply in a given nation, and a set of **age constraints**.

From that it found **several hundred genuinely different journeys** through the content, in about ten seconds.

Four things make those results representative rather than merely plentiful.

**Every option gets used.** Every possible answer appears at least once. Nothing is left untested because it was rare — and rare is where personalised plans usually go wrong.

**Difference is measured by the answers.** Two profiles count as the same only when they answer every question identically (the order of options within a multi-select doesn't count); one representative of each distinct answer set is kept. Without this you get tens of thousands of near-duplicates and no more real coverage.

Answers are the unit because answers are what the plan generator consumes: it is sent the readable question-answers plus age, and never the derived facts. So two profiles that differ in any answer may produce different plans and both are worth keeping — deduplicating on facts instead would collapse genuinely different inputs (a moped and a motorcycle share one vehicle fact) and under-test the generator. Facts are computed and carried on each profile only for review: the assertions a plan is graded against are built from them, and
they show at a glance why a plan came out the way it did. Because they never reach the generator, it must derive routing from the answers itself, exactly as it would for a real user.

**Dead ends are caught, not hidden.** The questionnaire is tested against thousands of invented answer sets to confirm every question can be reached,
every answer can appear, and every derived fact does real work. A question nobody could ever be asked is a bug, and models produce them regularly. Two of the faults this catches — a rule that never fires, a citation to a page that doesn't exist — produce output that otherwise looks perfect.

**People who couldn't exist are rejected.** Age isn't asked for, but it's constrained by the answers: someone who passed a driving test before 1997 is at least 46 today. Ages are calculated from the answers and handed to Claude as fixed, rather than invented alongside the persona. Across every journey found, zero produce an impossible person, and ages span the full legal range with a median that looks like a real learner population rather than a uniform draw.

The honest limitation: this tells you which journeys **exist**, not how **common** they are. The content can say a tractor journey is possible; it cannot say how many people take it. Frequency has to come from analytics or research.

---

## Reference

Takes a GOV.UK life-event content subgraph and produces a machine-executable
elicitation model — `questions`, `facts`, `option_filters`,
`numeric_constraints` — via Claude on Amazon Bedrock, then synthetic profiles
and review packets from that model.

Nothing in the file is specific to any life event. The only domain signal that
reaches the model is the corpus itself plus the `life_event` string from the
input JSON.

## Install

```bash
pip install -U boto3
export AWS_REGION=eu-west-2        # or use a profile / SSO / instance role
```

You need Bedrock model access enabled for the model you intend to use.

## Run

Two stages, with a human review checkpoint between them.

**1. Generate a questionnaire model to review:**

```bash
python plans.py model data/driving_subgraph.json \
    -o data/driving_model.json
```

This writes the model plus `data/driving_model.md`, a readable summary of every
question, fact and numeric constraint with its source. Review and amend
`data/driving_model.json` by hand.

| `model` flag | Default | Purpose |
|---|---|---|
| `-o`, `--out` | `data/model.json` | Where to write the generated questionnaire |
| `--summary` | `--out` with `.md` | Where to write the readable summary |
| `--repairs` | 3 | Validation rounds before giving up |
| `--seed` | 0 | Random seed, for reproducible profile sets |
| `--region` | `eu-west-2` | AWS region |

**2. Sample profiles from the reviewed model:**

```bash
python plans.py profiles data/driving_subgraph.json \
    --model data/driving_model.json \
    --profiles data/driving_profiles.json \
    --review data/driving_review.json \
    --personas
```

| `profiles` flag | Default | Purpose |
|---|---|---|
| `--model` | *required* | The reviewed / amended questionnaire to sample |
| `--profiles` | — | Write synthetic profiles here |
| `--review` | — | Write review packets here |
| `--personas` | off | Have Claude write a name and life for each profile |
| `--seed` | 0 | Random seed, for reproducible profile sets |
| `--region` | `eu-west-2` | AWS region |

The `profiles` stage **refuses to run if the amended model no longer
validates**, printing the specific issues so you can fix them before sampling —
generation guarantees a clean model, but a hand-edit does not. Sampling itself
is instant; only `--personas` calls Bedrock. The subgraph is still required,
because the validator needs it to check that every cited page exists.

Every Bedrock call prints its token usage to stderr as it happens, with a
running total, plus a final `total tokens` line once the run finishes — worth
watching, since one repair round-trip can dwarf every other call combined.

Exit code is 1 if validation issues remain, so this can gate a build.

## The model it produces

```json
{
  "meta":        { "life_event": "driving", "validation": "clean" },
  "questions":   [ { "id", "order", "text", "type", "ask_if", "options", "source" } ],
  "facts":       [ { "id", "description", "value" | ("type":"map","from","values"), "source" } ],
  "option_filters":     [ { "question_id", "option_id", "show_if" } ],
  "numeric_attributes": [ { "id", "unit", "description" } ],
  "numeric_constraints":[ { "attribute", "kind", "applies_if", "min", "max", "reason", "source" } ]
}
```

Conditions use a JsonLogic subset — `==`, `!=`, `>=`, `in`, `and`, `or`, `not`
— plus `any_option_has`, for a question that branches on a flag carried by
another question's options. A bare string resolves as a question or fact id.
`true` means always ask.

**Facts are what stop the model becoming a tree.** A rule like "does this
person need a theory test?" depends on five answers at once. In a decision tree
you would write it out at every leaf where it applies and keep all the copies
in step forever. Written once as a named fact, it is referenced wherever
needed.

**A fact may be a map** — `{"type": "map", "from": <question_id>, "values":
{...}}` — collapsing many answers into a few groups, so a question can be gated
on "any motorbike" rather than on six separate categories.

**Numeric constraints** bound attributes the questions never ask about. Three
kinds: `eligibility` where the corpus states it, `derived` where arithmetic
forces it, and `editorial` where it is your assumption and carries no source. A
derived bound is written as a date rather than a number —
`{"date_derived": {"date": "1997-01-01", "min_age_at_event": 17}}` — so it
resolves to 46 this year and 47 next year without anyone editing it.

An exception uses `overrides` to name the rule it replaces. This matters: a
rule letting a 16-year-old start early is not an additional floor to be
combined with the ordinary one, and an exception that only intersects is
silently swallowed by the stricter rule it was written to escape.

## The profiles it produces

```json
{
  "id": "P024",
  "answers":  { "q1_vehicle": "car", "q9_theory_support": ["audio_english"] },
  "readable": { "What do you want to learn to drive or ride?": "Car (category B)" },
  "numeric":  { "age": { "value": 43, "range": [42, 85],
                         "floor_because": "42 [derived] Passed a car test before February 2001..." } },
  "facts":    { "theory_exempt": false, "vehicle_group": "car_like" },
  "questions_asked": 11, "questions_skipped": 8,
  "persona":  { "name": "...", "circumstances": "...",
                "what_they_want": "...", "likely_friction": "..." }
}
```

`answers` is the payload — that is what a downstream plan generator consumes.
Everything else exists so a human can review the batch and so failures are
diagnosable: `readable` for eyeballing, `facts` for understanding why a plan
came out the way it did, `floor_because` for checking an age isn't nonsense.

Age draws decay from the minimum rather than spreading evenly, because uniform
across a legal range of `[17, 85]` gives a median learner driver of 51, which
describes nobody. Values sitting exactly on a legal boundary are over-sampled
on purpose — that is where plans break.

`persona` only appears with `--personas`, and not on every profile: personas
are written for the highest-risk profiles first, up to a cap that grows with
the square root of the profile count rather than linearly, so a model with far
more genuine branches doesn't multiply persona cost along with it.

## The review packets it produces

Each packet holds the profile, plus:

- **`assertions`** — the claims the plan must satisfy, each with the content
  path that justifies it. Around twelve per packet. Built from facts rather
  than question sources: a question's `source` is the same whichever answer was
  given, so it says nothing about this person, whereas a fact is computed from
  their answers. A `must_not_reflect` assertion matters as much as a positive
  one — a false exemption means the step stays in the plan, and a plan that
  drops it is wrong.
- **`risk`** — a score and its reasons, used to sort the file so limited human
  attention goes to the profiles most likely to expose a defect. Rare outcomes,
  boundary ages, and profiles where most questions were skipped all score
  higher.
- **`review_id`** — a hash of the plan shape rather than a sequential number,
  so review notes survive regeneration of the profile set.
- **`plan`** and **`review`** — empty slots for the generated plan and the human
  and LLM verdicts, so one file carries the work end to end.

`meta.rubric` holds the instructions for an LLM reviewer: judge against the
assertions rather than its own taste, then check the three things assertions
cannot cover — step order, omissions, and whether anything reads as written for
a different person.

### Write fact descriptions for reviewers

A fact's `description` becomes the reviewer-facing claim, so the prompt asks
for what a fact means for the *person* rather than how it is computed. "This
person does not need a theory test" is checkable; "collapses twelve options
into four groups" is not. Worth spot-checking on a new life event, because a
developer-facing description makes its assertion useless without making it look
wrong.

## Limits

Everything happens in one call per stage, with no checkpointing, caching or
batching. A failed run restarts from the beginning, and a corpus much larger
than driving's 92 pages (~90,000 tokens) may not fit a single prompt. If you
hit that ceiling, the multi-module version handles it.

The content cannot tell you how common a journey is, only that it exists.

---

# Part 2 — Ground truth and scoring (`truth.py`)

## What this is for

You are generating personalised plans and need to know whether they are any
good. That needs an answer key: for a given person, which steps should their
plan contain?

The obvious approach — ask a model to write the correct plan, then compare —
does not work. You end up comparing one model's prose against another's, with
no reason to believe either. The answer key has no more authority than the
thing it is judging.

This code takes a different route. GOV.UK already publishes step by steps:
ordered, hand-authored, editorially approved plans. "Learn to drive a car" has
seven steps. So the answer key is not new prose — it is that published spine,
with each step marked **required**, **not_required** or **blocked** for one
synthetic user.

## How it works

One file, three commands.

**`map` works out the rules.** It fetches a step by step live from GOV.UK and
asks Claude, once per guide, how the steps relate to your questionnaire: which
fact or answer decides each step, which answers stop part of the plan, and who
the guide covers. This is the only stage that calls a model.

**You review the mapping.** For the example driving mapping it is eight
decisions — four step rules, two blockers, two scope conditions. That is small
enough to check against the published guide in a sitting, which is the entire
point.

**`build` applies it.** Pure code, no AI, no network. Every profile gets a
verdict per step, each naming the fact or answer that produced it. A thousand
answer keys inherit one reviewed judgement rather than a thousand unreviewed
ones.

**`score` compares your plans.** Set arithmetic against the answer key,
reporting what was missed, what was added, and — counted separately — how many
people were shown a step they are not permitted to take.

## Why it's built this way

**Anchoring to a published spine avoids circularity.** The answer key inherits
GDS's editorial judgement about what the steps are and what order they come
in. Nothing in this repository decides that. The only judgement added is which
steps apply to whom, and that judgement is written down where you can see it.

**The AI writes a small artefact, not the output.** One mapping per guide,
reviewed once, then applied deterministically. This is the difference between
checking eight decisions and spot-checking hundreds of generated plans. It also
means a mapping error is systematic and visible rather than sporadic and
buried.

**A fixed step set makes scoring meaningful.** Precision and recall need a
closed universe of things that could have been included. Prose against prose
cannot be scored; sets of steps can.

**Blocked is not the same as not required.** A person who cannot legally
proceed — no permission to live in the UK for long enough, say — is different
from one who has already done a step. Presenting a blocked step is the most
damaging failure mode and the least likely to look wrong at a glance, so it is
tracked and reported separately from the F1 score rather than averaged into it.

## What you get, and why it can be trusted

*As in Part 1, the figures here are illustrative — one run against the driving
corpus, not a fixed guarantee. The exact counts move with the model, the
mapping and the profile set, so read them as a sketch rather than numbers to
reconcile against the committed data files.*

Against the driving corpus, the mapping produces answer keys for the subset of
profiles the "Learn to drive a car" guide covers, marking each of the guide's
**seven steps** required, not_required or blocked for that person.

Three things make those verdicts defensible.

**Every verdict names its evidence.** Not "step 4 was dropped" but
`theory_ahead=false`. A reviewer checks one named fact against the mapping
rather than re-deriving the reasoning, and a wrong verdict points straight at
the rule that caused it.

**The mapping is validated before it is used, twice.** `map` runs a structural
check — a rule naming a fact that does not exist, a rule carrying both a `fact`
and a `question`, a fact-form rule missing its boolean `drop_when`, a
question-form rule missing its `answers`, a step number out of range, two rules
on one step, an unknown question or answer in a blocker or in the scope, a
blocker pointing at a missing step, and the common slip of giving a question's
*text* where its *id* was meant. `build` re-runs that same structural check —
because a mapping can be hand-edited after `map` wrote it — and then adds two
checks that need the profile set: a rule or block keyed on a question no
in-scope profile ever reaches, and a block that fires for all or none of the
in-scope profiles (usually a sequencing prerequisite mistaken for a legal
gate). A failing check aborts the build rather than writing bad ground truth. A
mapping is small and applied silently to thousands of records, so a dangling
reference would otherwise fail invisibly.

**Blocks follow the guide's own dependencies.** The driving guide states that a
provisional licence is needed before lessons and a theory pass before booking
the practical. So blocking the provisional cascades forward. The cascade is in
the mapping, not hardcoded, and it is one of the things worth checking during
review.

The honest limitation: **a guide covers who it covers**. The driving step by
step is car-only and Great Britain only, so it produces answer keys for only
the car / Great Britain subset of profiles. Motorbike, lorry and tractor
journeys have no published spine.
Inventing one would reintroduce exactly the circularity this design exists to
avoid, so those profiles are out of scope rather than covered badly.

---

## Reference

Fetches GOV.UK step by steps by URL, maps them onto an elicitation model
produced by `plans.py`, and emits per-profile answer keys plus a scoring
command. Requires `plans.py` alongside it — it imports the model's fact
resolver.

Nothing is specific to any life event. The mapping stage adapts to whatever
guide and questionnaire it is given.

## Install

```bash
pip install -U boto3
export AWS_REGION=eu-west-2        # or use a profile / SSO / instance role
```

## Run

```bash
# 1. derive a mapping — one model call per guide
python truth.py map data/driving_model.json \
    --url https://www.gov.uk/learn-to-drive-a-car > data/mapping.json

# ... review data/mapping.json ...

# 2. apply it to every profile
python truth.py build data/driving_profiles.json data/driving_model.json data/mapping.json \
    > data/truth.json

# 3. score your app's plans
python truth.py score my_plans.json data/truth.json
```

Several guides at once, inline or from a file:

```bash
python truth.py map data/model.json --url https://www.gov.uk/a --url https://www.gov.uk/b
python truth.py map data/model.json --urls-file guides.txt
```

The URL file takes one per line; blank lines and `#` comments are ignored.
Full URLs, `www.gov.uk/...` and bare paths all work. A URL that fails is
reported and skipped rather than aborting the run, and the exit code is
non-zero if anything failed, so this can gate a build.

Guides are read from the GOV.UK content API
(`https://www.gov.uk/api/content/<slug>`), which returns the step structure as
JSON. No scraping, no dependence on page markup.

## The mapping

```json
{"mappings": [{
  "step_by_step": "/learn-to-drive-a-car",
  "rules": [
    {"step": 4, "fact": "theory_ahead", "drop_when": false,
     "why": "no theory test ahead"},
    {"step": 6, "question": "q1_vehicle", "answers": ["car"], "exclude": true,
     "why": "only relevant to car learners"}],
  "blocks": [
    {"question": "q6_permission_to_live", "answers": ["no", "unsure"],
     "steps": [2, 3, 4, 5, 6], "why": "cannot apply for a provisional"}],
  "scope": [
    {"question": "q1_vehicle", "answers": ["car"]},
    {"question": "q4_nation", "answers": ["northern_ireland"], "exclude": true}],
  "spine": [ ... the steps as fetched ... ]
}]}
```

**A rule comes in one of two forms.** A *fact-form* rule (`fact` + `drop_when`)
drops its step when a derived fact resolves to the given boolean — the right
choice when a step's relevance combines several answers, which is exactly what a
fact exists to capture. A *question-form* rule (`question` + `answers`, with an
optional `exclude`) drops its step based on a single raw answer, for the cases
where one question settles it and no fact is needed; `exclude` inverts the match,
so the example above keeps step 6 only for car learners. Exactly one form per
rule — carrying both is a validation error.

**`drop_when` is the field to check hardest.** Fact polarity has no convention:
`theory_ahead=true` means the theory steps apply, `theory_exempt=true` means
they do not. Same shape, opposite meaning. This cannot be inferred — an earlier
version guessed it from facts and steps citing the same pages and got one rule
in four right, while confidently suggesting `theory_exempt` where the answer
was `theory_ahead`.

**`scope` is a list because narrowing to a route is rarely enough.** The
driving guide covers cars, and also only Great Britain. One condition includes,
another excludes.

**`spine` is embedded**, so `build` and `score` need neither the network nor
the subgraph. The mapping is the complete artefact.

Hand-writing a mapping is entirely reasonable — it is eight decisions, and
`example_mapping_driving.json` shows the format. The rest of the pipeline does
not care where it came from.

## The answer keys

```json
{
  "profile_id": "P024",
  "step_by_step": "/learn-to-drive-a-car",
  "verdicts": [
    {"step": 4, "title": "Prepare for your theory test",
     "verdict": "not_required", "why": "theory_ahead=false"}
  ]
}
```

## Scoring

```json
{"summary": {
  "profiles": 83,
  "plans_without_ground_truth": 0,
  "mean_f1": 0.984,
  "perfect": 77,
  "presented_a_blocked_step": 0,
  "missed_a_required_step": 6
}}
```

`presented_a_blocked_step` is deliberately outside the F1 average: it is a
different class of failure and should not be traded off against coverage.

Plans are matched to answer keys by `profile_id`. A total mismatch is reported
as a mismatch and exits non-zero, rather than silently producing a mean F1 of
zero that reads like a broken app.

## Limits

One model call per guide, with no caching or retry. The mapping stage needs
network access to GOV.UK; nothing else does.

A guide is only as current as the moment you fetched it. Re-run `map` and
diff the mapping if GDS reorders a step.

---

# Part 3 — Calling the plan API (`run_app.py`)

## What this is for

The plan API returns free-text steps, not step numbers. Ground truth uses
step numbers from the GOV.UK spine. `run_app.py` bridges them: it calls the
API for each synthetic profile that has a ground-truth entry, maps the
returned tasks back onto spine step numbers by URL, and emits the plans in
the format `truth.py score` expects.

It also scores inline — comparing each plan against the ground truth as it
runs and writing aggregate metrics to `results.json` — so you get headline
numbers without a separate invocation.

## How it works

**It only calls the API for profiles with ground truth.** The driving guide
covers a subset of all profiles (car / Great Britain only). Calling the API
for profiles outside that scope produces plans that cannot be scored.

**It maps tasks to step numbers by URL.** Each task the API returns carries a
`gov_service_url`. The spine embedded in `truth.json` carries the GOV.UK
paths for each step. A URL that belongs to a spine step counts that step as
covered. No model call sits in this path — the mapping is exact and
deterministic.

**It scores as it runs.** After mapping each plan it calls the same scoring
function `truth.py score` uses and accumulates the per-profile results.
Aggregate precision, recall and F1 are ready by the time all profiles are
processed, with no second pass needed.

**It optionally judges relevance.** With `--relevance`, a separate Bedrock
call asks whether each task is relevant to this person's situation —
"relevant", "premature" or "irrelevant". This is a different question from
coverage: a task can be a valid GOV.UK page that is not a spine step at all
(vehicle tax, a booking confirmation), and relevance captures that where F1
cannot.

## Why it's built this way

**URL matching keeps the scoring path model-free.** Comparing the API's prose
step descriptions to spine step titles would need a model, introducing a
non-deterministic judgement between the app and its score. URL matching is
exact, repeatable, and cheap.

**Relevance is a separate metric, not a correction to F1.** Precision and
recall measure whether the right spine steps are covered. Relevance asks
whether the tasks are appropriate for this specific person. An app can score
1.0 on F1 while returning tasks irrelevant to the profile; it can also miss
spine steps while returning nothing irrelevant. Averaging incompatible signals
hides both failure modes, so they are kept apart.

**Scoring uses the same function as `truth.py score`.** `run_app.py` imports
`score` from `truth.py` directly, so the inline metrics and the standalone
scorer cannot diverge.

---

## Reference

Calls the plan API for each in-scope synthetic profile, maps returned tasks
onto spine step numbers, and writes scored plans to stdout and aggregate
metrics to `results.json`.

## Install

```bash
pip install -U boto3       # only needed for --relevance
export AWS_REGION=eu-west-1  # or use a profile / SSO / instance role
```

Bedrock credentials are only required with `--relevance`. The plan API and
everything else runs without AWS.

## Run

```bash
# Run all profiles and emit plans to stdout
python run_app.py data/driving_profiles.json data/truth.json > data/app_plans.json

# Test a single profile
python run_app.py data/driving_profiles.json data/truth.json --profile P011 --verbose

# Include LLM-judged relevance
python run_app.py data/driving_profiles.json data/truth.json --relevance > data/app_plans.json
```

The plan API must be running at `--endpoint` before calling this script.
`truth.json` is required — it carries the per-guide URL-to-step index used
to map the API's cited URLs onto step numbers.

| Flag | Default | Purpose |
|---|---|---|
| `--endpoint` | `http://localhost:8000/plan` | Plan API URL |
| `--profile` | — | Run one profile id only, for testing |
| `--raw` | — | Save full API responses here |
| `--verbose` | off | Print per-task URL trace to stderr |
| `--relevance` | off | Judge task relevance via Bedrock |
| `--relevance-model` | `eu.anthropic.claude-sonnet-4-5-20250929-v1:0` | Bedrock model for relevance judging |
| `--relevance-region` | `eu-west-1` | AWS region for relevance judging |
| `--results-out` | `results.json` | Where to write scoring and relevance results |

## The plans it produces

Emitted to stdout; pipe to a file and pass to `truth.py score` for the full
per-profile breakdown:

```json
{"plans": [
  {"profile_id": "P024", "step_by_step": "/learn-to-drive-a-car", "steps": [2, 4, 5, 6]}
]}
```

```bash
python truth.py score data/app_plans.json data/truth.json
```

## The results file

`results.json` (or `--results-out`) is written on every run:

```json
{"generated_at": "...", "scoring": {
  "aggregate": {
    "precision": 0.97, "recall": 0.95, "f1": 0.96,
    "mean_f1": 0.984, "profiles_scored": 83,
    "perfect": 77, "presented_a_blocked_step": 0, "missed_a_required_step": 6
  },
  "per_profile": [...]
}}
```

As with `truth.py score`, `presented_a_blocked_step` is kept outside the F1
average — it is a different class of failure and should not be traded off
against coverage.

With `--relevance`, a `"relevance"` key is added alongside `"scoring"`,
reporting aggregate counts of `relevant`, `premature` and `irrelevant`
verdicts and a per-profile breakdown. The relevance block carries a `"note"`
field as a reminder that it is LLM-judged and non-deterministic — report it
alongside precision/recall/F1, never folded into them.

## Limits

The plan API must be running and reachable at `--endpoint`. A failed API call
is reported on stderr and the profile is skipped rather than retried.

URLs cited by the app that are not in any guide's spine are reported on
stderr. They may be legitimate GOV.UK pages outside the step-by-step, or
miscited URLs that will never score — worth investigating if the unmatched
count is unexpectedly high.

Relevance judging makes one Bedrock call per profile.
