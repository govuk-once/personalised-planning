"""Prompts for generating a questionnaire from a corpus of government guidance."""

import json

SYSTEM_INTRO = """\
Read this government guidance corpus and design a questionnaire that decides \
what a person needs to do.

Only include a question if the corpus states different consequences for \
different answers. Look especially for eligibility gates, exemptions that \
remove a step entirely, date thresholds, geography where a nation is served \
by a different body, accessibility needs that must be declared in advance, \
and states that expire."""

# The first-question block comes in two variants (plans.py --main-goal).
# "required" is the original behaviour; "none" rules out any choice-of-service
# question, so people are routed on circumstances alone. An "optional" variant,
# letting the model choose whether to ask one, was tried and dropped: the model
# added `q_main_goal` as its first question anyway.
MAIN_GOAL_REQUIRED = """\
Your first question MUST have id `q_main_goal`, the lowest order of all \
questions, and be always asked (ask_if: true). It asks what the person wants \
to achieve — the top-level grouping of routes this life event covers. Its \
options are the distinct routes the corpus identifies for this life event; if \
the corpus only covers one service type, a single option is correct. Every \
other question must have a strictly higher order.

Two answers to `q_main_goal` can describe different STAGES of the same \
journey rather than different reasons someone is here — for example "get the \
document you need before you can start" versus "do the whole thing, start to \
finish." Do not split these into separate, mutually exclusive top-level \
options: someone doing the whole journey passes through its earlier stage too, \
and needs every question that stage would have asked. Model the earlier stage \
as a follow-up question instead — "do you already have X?" — asked within the \
fuller option, so the fuller option keeps every question and eligibility check \
the narrower one has, and adds its own on top."""

MAIN_GOAL_NONE = """\
Order questions so the earliest are the ones whose answers change the most of \
what follows — the questions that send people to different parts of the \
corpus. Ask early questions of everyone (ask_if: true) wherever you can.

Every question must ask about the person's circumstances: facts about them, \
their family, their work or their situation. Do not ask which service, topic \
or kind of help they want, under any id or wording — route people by their \
circumstances alone. Do not use the id `q_main_goal`."""

# Opt-in (plans.py --rationale), so runs without it keep their prompt unchanged.
RATIONALE = """\
Give every question a `rationale`: one sentence saying which parts of the \
corpus its answers send people to, and why it comes where it does in the \
order."""

MAIN_GOAL_BLOCKS = {
    "required": MAIN_GOAL_REQUIRED,
    "none": MAIN_GOAL_NONE,
}

SYSTEM_BODY = """\
Output four collections.

questions: id, order, text, type (single_select or multi_select), ask_if, \
options (id and label), source. Mark an option `"exclusive": true` if it \
cannot be chosen alongside others, such as "none of these". Mark an option \
with a flag like `"needs_evidence": true` if another question branches on it.

facts: id, description, value (a condition), source. A fact names a condition \
once so it is defined and checked in one place instead of being rewritten at \
every question that needs it. Emit a fact for every condition that either is \
read by more than one question or numeric_constraint, or combines more than \
one answer to decide whether a task, step or requirement applies to the \
person — "does this person need a theory test", "is this person exempt". A \
fact may instead be {"type": "map", "from": <question_id>, "values": {...}} \
to collapse many answers into a few named groups; use this whenever a \
question or rule depends on a category ("any motorbike") rather than the \
individual options. Write `description` as what this means for the PERSON — \
it is the claim a plan must satisfy and the text used to decide which steps \
the person needs, so "this person does not need a theory test" is useful and \
"collapses twelve options into four groups" is not.

option_filters: question_id, option_id, show_if — for answers that only apply \
to some people.

numeric_constraints: bounds on continuous attributes the questions do not \
ask about, such as age. Each has attribute, kind, applies_if, reason, source, \
and a min and/or max. kind is "eligibility" when the corpus states it, \
"derived" when arithmetic forces it, or "editorial" when it is your \
assumption and carries no source. A bound is {"value": n}, or \
{"date_derived": {"date": "yyyy-mm-dd", "min_age_at_event": n}} meaning the \
event happened before that date, so time has passed since. Give a constraint \
an `id` and list `overrides` when it is an exception that REPLACES another \
rather than adding to it — an exception that only intersects is silently \
swallowed by the stricter rule.

Also emit numeric_attributes: id, unit, description.

Bound every numeric attribute you declare, for every route that reaches it — \
use kind: "editorial" where the corpus gives no number. Point applies_if at the \
specific answer your reason describes, not a broader question that happens to \
include it. If your reason names two different thresholds for two different \
answers ("16 if X, 17 otherwise"), that is two constraints, not one — each \
with its own applies_if naming its own answer and its own number. A single \
constraint whose bound matches only one of the numbers your reason states \
means the other answer was never actually implemented.

Conditions use JsonLogic: {"==": [a, b]}, {"!=": [a, b]}, {"in": [a, [b]]}, \
{"and": [...]}, {"or": [...]}, {"not": [x]}, plus \
{"any_option_has": [question_id, flag]}. Bare strings resolve as question or \
fact ids — do NOT wrap them in {"var": ...}. `true` means always ask.

Order questions so anything referenced by an ask_if comes first{ordering}. \
Every source must be a base_path that appears in the corpus."""

ORDERING_REQUIRED = " — `q_main_goal` must have order 0 (or the lowest value used)"


def system_prompt(main_goal: str = "required", rationale: bool = False) -> str:
    """Assemble the model-generation system prompt.

    Args:
        main_goal: "required" forces `q_main_goal` as the first, always-asked
            question (the original prompt, text unchanged); "none" forbids any
            question about which service or help the person wants.
        rationale: Ask for a one-sentence `rationale` on every question.

    Returns:
        The system prompt text.
    """
    if main_goal not in MAIN_GOAL_BLOCKS:
        raise ValueError(
            f"main_goal must be one of {sorted(MAIN_GOAL_BLOCKS)}, got {main_goal!r}"
        )
    required = main_goal == "required"
    body = SYSTEM_BODY.replace("{ordering}", ORDERING_REQUIRED if required else "")
    parts = [SYSTEM_INTRO, MAIN_GOAL_BLOCKS[main_goal], body]
    if rationale:
        parts.append(RATIONALE)
    return "\n\n".join(parts)


SOURCE_SCHEMA = {"type": "array", "items": {"type": "string"}}

TOOL = {
    "name": "emit_model",
    "input_schema": {
        "type": "object",
        "properties": {
            "questions": {
                "type": "array",
                "items": {"type": "object", "properties": {"source": SOURCE_SCHEMA}},
            },
            "facts": {
                "type": "array",
                "items": {"type": "object", "properties": {"source": SOURCE_SCHEMA}},
            },
            "option_filters": {"type": "array", "items": {"type": "object"}},
            "numeric_attributes": {"type": "array", "items": {"type": "object"}},
            "numeric_constraints": {
                "type": "array",
                "items": {"type": "object", "properties": {"source": SOURCE_SCHEMA}},
            },
        },
        "required": ["questions", "facts", "option_filters"],
    },
}


def tool_schema(rationale: bool = False) -> dict:
    """The emit_model tool, with a `rationale` string on questions if asked for."""
    if not rationale:
        return TOOL
    tool = json.loads(json.dumps(TOOL))
    tool["input_schema"]["properties"]["questions"]["items"]["properties"][
        "rationale"
    ] = {"type": "string"}
    return tool


REPAIR = """\
Fix only what these errors identify, plus whatever is needed to make those \
fixes coherent. Do not redesign the question set, and do not delete questions \
or facts to make an error disappear — fix the logic or the answers a fact \
reads instead, and delete a fact only if the distinction it draws genuinely \
does not exist in the corpus. Emit the corrected model in full."""

PERSONA_SYSTEM = """\
Invent a plausible person who would give these answers.

The answers and the age are FIXED and already checked. Use the age exactly; \
do not adjust it or describe the person in a way implying a different one. \
Explain why they are in this situation rather than restating their answers. \
Vary demography and confidence with technology across the set."""

PERSONA_TOOL = {
    "name": "write_persona",
    "input_schema": {
        "type": "object",
        "properties": {
            "name": {"type": "string"},
            "circumstances": {"type": "string"},
            "what_they_want": {"type": "string"},
            "likely_friction": {"type": "string"},
        },
        "required": ["name", "circumstances", "what_they_want"],
    },
}


MAP_SYSTEM = """\
You are mapping a GOV.UK step-by-step guide onto a questionnaire, so that a \
person's answers decide which steps they need.

You are given the guide's steps and the questionnaire's facts and questions. \
The questionnaire may cover several unrelated services — most of it will not \
apply here. Work out the scope condition first (see SCOPE below), then check \
every question's ask_if against it: a question only reachable under a \
different answer was never asked of anyone this guide is for, and cannot \
produce a rule or block. A question reachable under THIS guide's scope \
condition was asked of everyone it covers, and deserves a real check against \
every step — do not stop at the first one you find.

Everywhere you name a question or a fact, use its `id` — the short token like `already_have_provisional`, never the question text — and name answers by their option `id`, not their label. The ids are what the mapping is checked and applied by; the text and labels are only there to help you read the questionnaire.

Produce three things.

RULES: for each step whose relevance depends on the person, say what decides \
it. Two ways to write a rule — use whichever fits.

Prefer a FACT when one already fits: name the ONE fact that decides the step \
(or one of its conditions — see below), and say whether the step drops out when that fact is true or when it is \
false. Polarity matters and has no convention: a fact meaning "a test lies \
ahead" drops its step when false, while a fact meaning "exempt from the test" \
drops it when true. Read each fact's description rather than its name.

Write a QUESTION rule directly when no fact captures it — an England-and-Wales \
scheme when the person lives in Scotland, a step about children when they \
have none, and nothing in the questionnaire's facts already says so. Name the \
question and the answers involved. By default the step drops out for anyone \
who did NOT give one of those answers — the answers are what the step needs. \
Set exclude true if instead those answers are what disqualifies the step, \
and everyone else keeps it — the reverse case.

Do not invent a fact to work around this; cite the question and answers \
directly. Omit any step that applies to everyone.

A step that needs several conditions at once gets one rule per condition. \
It drops out if any of its rules drops it, so it stays only for people who \
meet every condition. Rules combine only this way: if a step applies when \
EITHER of two different questions is satisfied, no set of rules can express \
it — use a fact that captures it, or leave that condition out.

A plan covers the whole journey ahead, not only what the person must do now. \
A step later in the journey still applies to someone at an earlier stage: \
do not drop it because they have not reached it yet. Drop a step for stage \
only when the person is past it and it no longer applies — for example, \
steps to take before a birth, once the baby is born.

Check in particular for a question asking whether the person already holds \
what this guide leads towards, or has already done what an early step asks — \
a guide that gets someone a licence or credential almost always has one, \
gated on this guide's own scope condition, and it is easy to overlook among \
questions belonging to other services. If it exists, the step that grants or \
does that thing drops out for people who already have it.

BLOCKS: a block marks a step this person is legally NOT PERMITTED to take, not \
one that merely does not apply to them. Reserve it for a hard gate the guide \
states: no right to live in the UK long enough to apply, below a legal minimum \
with no exception, and the like. Key each block on the questionnaire answers \
that trigger the gate and list the steps it shuts. A gate also shuts the steps \
the guide says depend on the gated one — if applying is barred and a later \
step needs that application, it is barred too. A question carrying a \
blocker_type is known to gate something; use it to find the gate, but decide \
the steps yourself.

A block must divide the people the guide covers: on the strength of their \
answers it applies to some and not others. A condition that would block a step \
for EVERYONE in scope is not a personal gate but the guide's own running order \
— "you need a provisional licence before booking a theory test", "you must \
pass the theory before the practical". That order is already carried by the \
step numbers; those later steps stay relevant and belong in the plan, just \
later. Do not block them. Wrongly showing a step is a small error, but wrongly \
telling someone to take a step they are barred from is the worst error there \
is, so the two are kept apart. Most guides have no blocks at all; a block on \
every step after the first is this mistake, not a mapping.

SCOPE: who this guide is for. A guide covering one route through a life event \
must not be used to judge plans for the others. Give one condition per \
question — the answers the guide covers, or the answers it excludes. A guide \
served by a different body in one nation should exclude that nation, not just \
narrow the route. Leave scope out only if the guide genuinely covers everyone.

A corpus spanning several services always asks up front which one the \
person wants via `q_main_goal` — that question's answer is always the \
primary scope condition. Nobody is legally barred from wanting the wrong \
service; the guide simply does not cover them. \
If you find yourself writing a block whose steps list would be empty because \
nothing is actually being shut, that question decides who the guide is for \
and belongs in scope instead.

Be conservative. A wrong rule is applied silently to every profile, so omit \
anything you cannot justify from the guide's own text and the fact \
descriptions."""

# The SCOPE paragraph above assumes the questionnaire opens with `q_main_goal`.
# A model generated with `plans.py --main-goal none` routes people by
# circumstances instead, so its mapping takes scope from those. `map_system` / `map_tool` swap the text in;
# a model that has `q_main_goal` still gets MAP_SYSTEM and MAP_TOOL unchanged.
MAP_SCOPE_GOAL = """\
A corpus spanning several services always asks up front which one the \
person wants via `q_main_goal` — that question's answer is always the \
primary scope condition. Nobody is legally barred from wanting the wrong \
service; the guide simply does not cover them. \
If you find yourself writing a block whose steps list would be empty because \
nothing is actually being shut, that question decides who the guide is for \
and belongs in scope instead."""

MAP_SCOPE_CIRCUMSTANCES = """\
This questionnaire does not ask which service the person wants: it routes \
people by their circumstances. Work out who the guide is for from those \
circumstances — where they live, what stage of the life event they are at, \
their relationship to the person or event the guide is about — and express \
it as scope, one condition per question. Nobody is legally barred by being \
outside a guide's scope; the guide simply does not cover them. If you find \
yourself writing a block whose steps list would be empty because nothing is \
actually being shut, that question decides who the guide is for and belongs \
in scope instead."""

MAP_SCOPE_TOOL_GOAL = (
    "Conditions a profile must satisfy for this "
    "guide to apply — a corpus spanning several services needs at "
    "least the one that selects this service. Use an empty list "
    "only if the guide genuinely covers everyone."
)

MAP_SCOPE_TOOL_CIRCUMSTANCES = (
    "Conditions on the person's circumstances that a profile must satisfy for "
    "this guide to apply. Use an empty list only if the guide genuinely "
    "covers everyone."
)


def map_system(has_main_goal: bool = True) -> str:
    """The mapping system prompt, with scope wording to suit the model.

    Args:
        has_main_goal: Whether the questionnaire has a `q_main_goal` question.

    Returns:
        MAP_SYSTEM unchanged if it does; otherwise the version whose SCOPE
        guidance works from the person's circumstances.
    """
    if has_main_goal:
        return MAP_SYSTEM
    return MAP_SYSTEM.replace(MAP_SCOPE_GOAL, MAP_SCOPE_CIRCUMSTANCES)


def map_tool(has_main_goal: bool = True) -> dict:
    """The mapping tool schema, with the scope description to suit the model."""
    if has_main_goal:
        return MAP_TOOL
    tool = json.loads(json.dumps(MAP_TOOL))
    tool["input_schema"]["properties"]["scope"]["description"] = (
        MAP_SCOPE_TOOL_CIRCUMSTANCES
    )
    return tool


MAP_TOOL = {
    "name": "emit_mapping",
    "input_schema": {
        "type": "object",
        "properties": {
            "rules": {
                "type": "array",
                "description": "Two forms. Fact-form: step + fact + drop_when. "
                "Question-form, when no fact fits: step + question + answers, "
                "with optional exclude. Use exactly one form per rule.",
                "items": {
                    "type": "object",
                    "properties": {
                        "step": {"type": "integer"},
                        "fact": {"type": "string"},
                        "drop_when": {
                            "type": "boolean",
                            "description": "Fact-form only. Step drops out "
                            "when the fact equals this.",
                        },
                        "question": {"type": "string"},
                        "answers": {"type": "array", "items": {"type": "string"}},
                        "exclude": {
                            "type": "boolean",
                            "description": "Question-form only. False "
                            "(default): step drops out unless the answer is "
                            "one of these. True: step drops out if the "
                            "answer is one of these.",
                        },
                        "why": {"type": "string"},
                    },
                    "required": ["step", "why"],
                },
            },
            "blocks": {
                "type": "array",
                "description": "Steps a person is legally barred from taking, "
                "keyed on the answers that bar them. Not steps that merely do "
                "not apply — those are rules. A block must apply to some "
                "in-scope people and not others.",
                "items": {
                    "type": "object",
                    "properties": {
                        "question": {"type": "string"},
                        "answers": {"type": "array", "items": {"type": "string"}},
                        "steps": {"type": "array", "items": {"type": "integer"}},
                        "why": {"type": "string"},
                    },
                    "required": ["question", "answers", "steps", "why"],
                },
            },
            "scope": {
                "type": "array",
                "description": MAP_SCOPE_TOOL_GOAL,
                "items": {
                    "type": "object",
                    "properties": {
                        "question": {"type": "string"},
                        "answers": {"type": "array", "items": {"type": "string"}},
                        "exclude": {
                            "type": "boolean",
                            "description": "True to EXCLUDE these "
                            "answers rather than require them.",
                        },
                    },
                    "required": ["question", "answers"],
                },
            },
        },
        "required": ["rules", "blocks", "scope"],
    },
}
