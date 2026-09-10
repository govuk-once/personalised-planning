r"""Elicitation models and synthetic profiles from GOV.UK content, in one file.

Two stages, with a human review checkpoint between them:

  python plans.py model data/subgraph.json -o data/model.json
      # generate a questionnaire model + data/model.md summary to review

  # a human reviews and amends data/model.json here

  python plans.py profiles data/subgraph.json --model data/model.json \\
      --profiles data/out.json --review data/review.json --personas
      # sample the reviewed model; refuses to run if it no longer validates
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import random
import re
import statistics
import sys
from datetime import date
from pathlib import Path

from prompts import SYSTEM, TOOL, REPAIR, PERSONA_SYSTEM, PERSONA_TOOL
from summary import summarize

INF = math.inf
MAX_MULTI_SELECT = 3  # cap prevents unrealistically exhaustive selections

# --------------------------------------------------------------------------
# corpus
# --------------------------------------------------------------------------


def load_corpus(path: str) -> tuple[str, str, set[str]]:
    """Flatten a subgraph into one prompt block.

    Args:
        path: Path to the life-event subgraph JSON.

    Returns:
        A tuple of (life_event, prompt_text, citable_paths). Citable paths
        include `page/part-slug` for multi-part guides, because guidance is
        cited at section level far more often than page level.
    """
    graph = json.loads(Path(path).read_text())
    chunks, paths = [], set()
    for node in graph.get("nodes", []):
        base = node.get("base_path", "")
        paths.add(base)
        raw = node.get("details") or ""
        for slug in re.findall(r'"slug":\s*"([^"]+)"', raw):
            paths.add(f"{base}/{slug}")
        text = re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", raw))[:5000]
        chunks.append(f"### {node.get('title')} ({base})\n{text}")
    return graph.get("life_event", "unknown"), "\n\n".join(chunks), paths


def call(client, system, user, tool, max_tokens=32_000, usage=None):
    """Make one request that must come back as a tool call.

    Args:
        client: A boto3 bedrock-runtime client.
        system: System prompt.
        user: User message.
        tool: Tool schema the response must conform to.
        max_tokens: Response token ceiling.
        usage: Optional dict accumulating input/output token counts.

    Returns:
        The tool input the model produced.

    Raises:
        RuntimeError: If the model replied without calling the tool.
    """
    response = client.converse(
        modelId="eu.anthropic.claude-sonnet-5",
        inferenceConfig={"maxTokens": max_tokens},
        system=[{"text": system}],
        messages=[{"role": "user", "content": [{"text": user}]}],
        toolConfig={
            "tools": [
                {
                    "toolSpec": {
                        "name": tool["name"],
                        "inputSchema": {"json": tool["input_schema"]},
                    }
                }
            ],
            "toolChoice": {"tool": {"name": tool["name"]}},
        },
    )
    if usage is not None:
        u = response.get("usage", {})
        usage["input"] = usage.get("input", 0) + u.get("inputTokens", 0)
        usage["output"] = usage.get("output", 0) + u.get("outputTokens", 0)
        # Per-call, since one repair round-trip can dwarf every other call combined.
        print(
            f"tokens: {u.get('inputTokens', 0)} in / {u.get('outputTokens', 0)} out "
            f"(running total {usage['input'] + usage['output']})",
            file=sys.stderr,
        )
    for block in response["output"]["message"]["content"]:
        if "toolUse" in block:
            return block["toolUse"]["input"]
    raise RuntimeError(f"no tool call; stop_reason={response.get('stopReason')}")


# --------------------------------------------------------------------------
# evaluate
# --------------------------------------------------------------------------


def resolve(model, name, answers, seen=()):
    """Look up an answer or compute a fact.

    Map facts must be handled here. Falling through to the boolean path
    returns False for every one of them, which silently kills every question
    gated on a group — no error, just questions never asked.

    Args:
        model: The elicitation model.
        name: A question id or fact id.
        answers: Answers given so far.
        seen: Fact ids already being resolved, to stop cycles.

    Returns:
        The answer, the fact's value, or None if neither exists.
    """
    if name in answers:
        return answers[name]
    fact = {f["id"]: f for f in model.get("facts", [])}.get(name)
    if not fact or name in seen:
        return None
    if fact.get("type") == "map":
        inner = resolve(model, fact.get("from", ""), answers, seen + (name,))
        return fact.get("values", {}).get(inner)
    return ev(model, fact.get("value", False), answers, seen + (name,))


def ev(model, node, answers, seen=()):
    """Evaluate a JsonLogic condition.

    Args:
        model: The elicitation model.
        node: A condition dict, or a bare bool.
        answers: Answers given so far.
        seen: Fact ids already being resolved, to stop cycles.

    Returns:
        True if the condition holds. A comparison against an unanswered
        question is always False.

    Raises:
        ValueError: If the condition uses an unknown operator.
    """
    if isinstance(node, bool):
        return node
    if not isinstance(node, dict) or not node:
        return False
    op, args = next(iter(node.items()))

    def side(x):
        if isinstance(x, dict):
            return ev(model, x, answers, seen)
        if isinstance(x, str):
            v = resolve(model, x, answers, seen)
            return x if v is None else v
        return x

    if op == "and":
        return all(ev(model, a, answers, seen) for a in args)
    if op == "or":
        return any(ev(model, a, answers, seen) for a in args)
    if op == "not":
        return not ev(model, args[0], answers, seen)
    if op == "==":
        # No special case for unanswered questions: `side` returns the bare
        # id string when it cannot resolve one, so "q1_vehicle" == "car" is
        # already False. Guarding on None here instead makes two equal
        # literals compare unequal.
        return side(args[0]) == side(args[1])
    if op == "!=":
        return side(args[0]) != side(args[1])
    if op == ">=":
        a, b = side(args[0]), side(args[1])
        return isinstance(a, (int, float)) and isinstance(b, (int, float)) and a >= b
    if op == "in":
        return side(args[0]) in args[1]
    if op == "any_option_has":
        raw = resolve(model, args[0], answers, seen)
        selected = [raw] if isinstance(raw, str) else (raw or [])
        options = {
            o["id"]: o
            for q in model["questions"]
            if q["id"] == args[0]
            for o in q["options"]
        }
        return any(options.get(s, {}).get(args[1]) for s in selected)
    if op == "var":
        # Not part of the documented spec, but standard JsonLogic and what a
        # bare id string already does here, so treat it the same rather than
        # reject a model for using the syntax it was trained on.
        name = args[0] if isinstance(args, list) else args
        return side(name)
    raise ValueError(f"unknown operator {op!r}")


def visible(model, q, answers):
    """List the options shown for a question given prior answers.

    Args:
        model: The elicitation model.
        q: The question being asked.
        answers: Answers given so far.

    Returns:
        Option ids passing their option_filters entry.
    """
    blocked = {
        f["option_id"]
        for f in model.get("option_filters", [])
        if f["question_id"] == q["id"]
        and not ev(model, f.get("show_if", True), answers)
    }
    return [o["id"] for o in q["options"] if o["id"] not in blocked]


def walk(model, rng):
    """Answer the model once, at random, honouring ask/skip and filters.

    Args:
        model: The elicitation model.
        rng: Seeded random source.

    Returns:
        Answers keyed by question id, for asked questions only.
    """
    answers = {}
    for q in sorted(model["questions"], key=lambda q: q.get("order", 0)):
        if not ev(model, q.get("ask_if", True), answers):
            continue
        opts = visible(model, q, answers)
        if not opts:
            continue
        if q.get("type") == "multi_select":
            # An exclusive option cannot sit alongside a real selection.
            # Without this, "none of these" appears with genuine needs in
            # about a fifth of answers — people who do not exist.
            ex = {o["id"] for o in q["options"] if o.get("exclusive")}
            gate = [o for o in opts if o in ex]
            rest = [o for o in opts if o not in ex]
            if gate and (not rest or rng.random() < 1.0 / len(opts)):
                answers[q["id"]] = [gate[0]]
            else:
                pool = rest or opts
                answers[q["id"]] = rng.sample(
                    pool, rng.randint(1, min(MAX_MULTI_SELECT, len(pool)))
                )
        else:
            answers[q["id"]] = rng.choice(opts)
    return answers


def signature(model, answers):
    """Which route through the content this profile takes.

    Args:
        model: The elicitation model.
        answers: The profile's answers.

    Returns:
        A hashable signature. Equal signatures mean equal plans.
    """
    # sorted(answers) sorts the dict's keys only, dropping every value, so
    # two different answers to the same questions collapsed into one
    # signature and one was discarded silently.
    #
    # Multi-select values are sorted before tupling: walk() fills them with
    # rng.sample, whose order is random, so without this the same set of
    # selected options in a different order signs as a distinct profile —
    # order noise that keeps duplicates the dedup is meant to remove.
    given = tuple(
        sorted(
            (qid, tuple(sorted(v)) if isinstance(v, list) else v)
            for qid, v in answers.items()
        )
    )
    return (
        given,
        tuple(
            sorted(
                (f["id"], str(resolve(model, f["id"], answers)))
                for f in model.get("facts", [])
            )
        ),
    )


def generate(model, budget=20_000, seed=0):
    """Sample hard, keep one profile per distinct plan shape.

    Deduplicating on answers alone keeps roughly nine near-identical plans
    for every distinct one. Brute force reaches full option coverage in
    under four seconds, which is why there is no directed search here.

    Args:
        model: The elicitation model.
        budget: How many walks to attempt.
        seed: Random seed, for reproducibility.

    Returns:
        One representative profile per distinct signature.
    """
    rng = random.Random(seed)
    seen = {}
    for _ in range(budget):
        a = walk(model, rng)
        seen.setdefault(signature(model, a), a)
    return list(seen.values())


# --------------------------------------------------------------------------
# age
# --------------------------------------------------------------------------


def years_since(iso, today):
    """Count whole years between an ISO date and today.

    Args:
        iso: Date in yyyy-mm-dd form.
        today: Date to measure to.

    Returns:
        Whole years elapsed.
    """
    y, m, d = (int(x) for x in iso.split("-"))
    return (today.year - y) - ((today.month, today.day) < (m, d))


def bound(spec, today):
    """Resolve one bound to a number.

    Args:
        spec: A bound holding either `value` or `date_derived`.
        today: Date the derivation is relative to.

    Returns:
        The bound as a number.

    Raises:
        ValueError: If the bound has neither form.
    """
    if "value" in spec:
        return float(spec["value"])
    dd = spec.get("date_derived")
    if not dd:
        raise ValueError(f"bound has neither value nor date_derived: {spec}")
    return years_since(dd["date"], today) + float(dd.get("min_age_at_event", 0))


def solve(model, answers, attribute, today=None):
    """Compute the legal range for one attribute.

    Intersection alone cannot express an exception: a rule letting a
    16-year-old start early replaces the ordinary floor rather than being
    maxed against it. `overrides` disables what an exception supersedes.

    Args:
        model: The elicitation model, including numeric_constraints.
        answers: The person's answers.
        attribute: Attribute id, such as 'age'.
        today: Date used for date-derived bounds.

    Returns:
        A dict with lo, hi, why_lo, why_hi and empty. An empty range means
        the answers describe nobody.
    """
    today = today or date.today()
    active = [
        c
        for c in model.get("numeric_constraints", [])
        if c.get("attribute") == attribute
        and ev(model, c.get("applies_if", True), answers)
    ]
    suppressed = {o for c in active for o in c.get("overrides", []) or []}
    active = [c for c in active if c.get("id") not in suppressed]

    lo, hi, why_lo, why_hi = 0.0, INF, None, None
    floored = False
    for c in active:
        tag = f"[{c.get('kind', 'eligibility')}] {c.get('reason', '')}"
        if "min" in c:
            v = bound(c["min"], today)
            floored = True  # a constraint applied, even if it didn't move lo
            if v > lo:
                lo, why_lo = v, f"{v:g} {tag}"
        if "max" in c:
            v = bound(c["max"], today)
            if v < hi:
                hi, why_hi = v, f"{v:g} {tag}"
    return {
        "lo": lo,
        "hi": hi,
        "why_lo": why_lo,
        "why_hi": why_hi,
        "empty": lo > hi,
        # True when some constraint set a minimum for these answers, even
        # one that happened to equal the default of 0.0 and so left why_lo
        # unset. Without tracking this separately, a legitimate "min: 0"
        # constraint is indistinguishable from no constraint at all, and
        # gets wrongly reported as an unfloored route.
        "floored": floored,
    }


def draw_age(rng, span, ceiling=80.0):
    """Draw a legal value from a solved range.

    Bounds may be fractional, so rounding goes inward on both sides:
    truncating a floor of 15.75 emits people below the legal minimum. The
    draw decays from the floor, because uniform over a sixty-year range
    gives a median nobody recognises, and boundary values are over-sampled
    because that is where plans break.

    Despite the name this draws any numeric attribute, not just age.
    `ceiling` exists only to give an unbounded-above range a finish line —
    it must never override a real declared maximum. `min(span["hi"],
    ceiling)` did exactly that: every attribute measured in something
    other than years (days, months) had its true upper bound silently
    replaced by 80, because 80 looks like a plausible number for age and
    nothing else.

    Args:
        rng: Seeded random source.
        span: A range from `solve`.
        ceiling: Used only when the range has no upper bound at all.

    Returns:
        A value inside the range, or None if the range is empty.
    """
    if span["empty"]:
        return None
    lo = math.ceil(span["lo"])
    hi = span["hi"] if span["hi"] != INF else max(span["lo"] + 1, ceiling)
    hi = math.floor(hi)
    if hi < lo:
        return float(lo)
    if rng.random() < 0.25:
        return float(rng.choice([x for x in (lo, lo + 1, hi, hi - 1) if lo <= x <= hi]))
    decay = rng.expovariate(1.0 / max((hi - lo) / 4.0, 1.0))
    return float(min(int(lo + decay), hi))


# --------------------------------------------------------------------------
# validate
# --------------------------------------------------------------------------


def refs(node, out):
    """Collect referenced ids and the literals they are compared to.

    Args:
        node: A condition dict to walk.
        out: List that (id, literal) pairs are appended to.
    """
    if not isinstance(node, dict) or not node:
        return
    op, args = next(iter(node.items()))
    if op in {"and", "or"}:
        for a in args:
            refs(a, out)
    elif op == "not":
        refs(args[0], out)
    elif op in {"==", "!=", ">="}:
        if isinstance(args[0], str):
            out.append((args[0], args[1]))
    elif op == "in":
        if isinstance(args[0], str):
            for lit in args[1]:
                out.append((args[0], lit))
        else:
            out.append((None, f"malformed 'in' condition: {node}"))
    elif op == "any_option_has" and isinstance(args[0], str):
        out.append((args[0], None))


def as_list(value):
    """Coerce a possibly-missing, possibly-bare-string field to a list.

    A source is meant to be a list of base_paths, but a model sometimes emits
    a bare string instead. Iterating a string walks its characters, not the
    whole path, so that has to be caught here rather than where it is used.

    Args:
        value: None, a string, or a list.

    Returns:
        A list, wrapping a bare string as its single element.
    """
    if value is None:
        return []
    return [value] if isinstance(value, str) else value


def fact_refs(model, fid, seen=()):
    """Question ids a fact's condition reads, directly or via other facts.

    Args:
        model: The elicitation model.
        fid: A fact id.
        seen: Fact ids already expanded, to stop cycles.

    Returns:
        A set of question ids.
    """
    facts = {f["id"]: f for f in model.get("facts", [])}
    questions = {q["id"] for q in model.get("questions", [])}
    fact = facts.get(fid)
    if not fact or fid in seen:
        return set()
    found = []
    if fact.get("type") == "map":
        found = [(fact.get("from"), None)]
    else:
        refs(fact.get("value", False), found)
    out = set()
    for ref, _ in found:
        if ref in questions:
            out.add(ref)
        elif ref in facts:
            out |= fact_refs(model, ref, seen + (fid,))
    return out


def fact_reachable(model, fid, answers):
    """Whether a fact was ever actually in play for this profile.

    A fact reads one or more questions. If every one of them was asked on
    this person's route, a False result is a real negative — "you don't
    need CBT because you said you're exempt" is worth telling a reviewer.
    If a referenced question was never asked at all, the person's route
    never came near the topic, and asserting the negative just repeats
    "you don't need a taxi licence" to someone learning to drive a car —
    true, but not a finding, and it crowds out the assertions that are.

    Args:
        model: The elicitation model.
        fid: A fact id.
        answers: The profile's answers.

    Returns:
        True if every question the fact reads was asked for this profile.
    """
    return fact_refs(model, fid) <= set(answers)


def _check_condition_refs(label, cond, questions, known, errs):
    """Check a condition expression for unknown ids and invalid option literals.

    Walks ``cond`` with :func:`refs` and appends to ``errs`` for any referenced
    id not in ``known``, or any string literal compared against a question whose
    options don't include it.

    Args:
        label: Human-readable prefix for error messages (e.g. ``"fact f1.value"``).
        cond: Condition expression to walk (a dict, bool, or ``None``).
        questions: Mapping of question id to question dict.
        known: Set of all valid ids (questions and facts).
        errs: List to append error strings to.
    """
    found = []
    refs(cond, found)
    for ref, literal in found:
        if not isinstance(ref, str):
            continue
        if ref not in known:
            errs.append(f"{label}: unknown id '{ref}'")
        elif ref in questions:
            opts = {o["id"] for o in questions[ref]["options"]}
            if (
                isinstance(literal, str)
                and literal not in opts
                and literal not in known
            ):
                errs.append(
                    f"{label} compares {ref} to '{literal}', "
                    f"which is not one of its options"
                )


def validate(model, paths, profiles):
    """Check the model resolves and that nothing in it is dead.

    Covers only the four fault classes measurement showed ship invisibly:
    a near-miss option id, an unsatisfiable condition, a fact that never
    varies, and a fabricated source. The last two produce output that looks
    entirely normal, which is why they need a checker at all.

    The dynamic half reuses profiles already generated, so it costs nothing
    beyond the walk that was happening anyway.

    Args:
        model: The elicitation model.
        paths: Citable paths, from `load_corpus`.
        profiles: Sampled answer sets to check reachability against.

    Returns:
        Error strings, empty if the model is sound.
    """
    errs = []
    questions = {q["id"]: q for q in model.get("questions", [])}
    facts = {f["id"]: f for f in model.get("facts", [])}
    known = set(questions) | set(facts)

    # Structural checks first: a duplicate id silently overwrites the earlier
    # definition in the answer dict, so a later question's options replace the
    # first one's and every fact reading it resolves to None. An empty option
    # list surfaces only as a confusing complaint about some other question
    # comparing against an option that no longer exists.
    main_goal = questions.get("q_main_goal")
    if not main_goal:
        errs.append("q_main_goal: missing — the first question must have this id")
    else:
        if main_goal.get("order", 0) != min(
            q.get("order", 0) for q in model.get("questions", [])
        ):
            errs.append("q_main_goal: must have the lowest order of all questions")
        ask = main_goal.get("ask_if", True)
        if ask is not True:
            errs.append(
                "q_main_goal: must be always asked (ask_if must be true or absent)"
            )

    if len(questions) != len(model.get("questions", [])):
        seen = set()
        for q in model.get("questions", []):
            if q["id"] in seen:
                errs.append(f"{q['id']}: duplicate question id")
            seen.add(q["id"])
    for qid, q in questions.items():
        if not q.get("options"):
            errs.append(f"{qid}: has no options")
        elif len({o["id"] for o in q["options"]}) != len(q["options"]):
            errs.append(f"{qid}: duplicate option ids")
    if any(fid in questions for fid in facts):
        errs += [
            f"fact {fid}: id collides with a question id"
            for fid in facts
            if fid in questions
        ]
    for i, c in enumerate(model.get("numeric_constraints", [])):
        if not isinstance(c, dict):
            errs.append(
                f"numeric_constraints[{i}]: expected an object, got {type(c).__name__!r}"
            )
    if errs:
        return errs

    for qid, q in questions.items():
        for src in as_list(q.get("source")):
            if src not in paths:
                errs.append(f"{qid}: source '{src}' is not in the corpus")
        found = []
        refs(q.get("ask_if", True), found)
        for ref, literal in found:
            if not isinstance(ref, str):
                continue
            if ref not in known:
                continue
            if ref in questions:
                if questions[ref].get("order", 0) >= q.get("order", 0):
                    errs.append(f"{qid}.ask_if reads {ref}, asked no earlier")
                opts = {o["id"] for o in questions[ref]["options"]}
                if (
                    isinstance(literal, str)
                    and literal not in opts
                    and literal not in known
                ):
                    errs.append(
                        f"{qid}.ask_if compares {ref} to '{literal}', "
                        f"which is not one of its options"
                    )
    for fid, f in facts.items():
        for src in as_list(f.get("source")):
            if src not in paths:
                errs.append(f"fact {fid}: source '{src}' is not in the corpus")
        _check_condition_refs(
            f"fact {fid}.value", f.get("value", False), questions, known, errs
        )
    for i, filt in enumerate(model.get("option_filters", [])):
        q = questions.get(filt.get("question_id"))
        if not q:
            errs.append(f"option_filters[{i}]: unknown question")
        elif filt.get("option_id") not in {o["id"] for o in q["options"]}:
            errs.append(
                f"option_filters[{i}]: "
                f"'{filt.get('option_id')}' is not an option of {q['id']}"
            )
        _check_condition_refs(
            f"option_filters[{i}].show_if",
            filt.get("show_if", True),
            questions,
            known,
            errs,
        )
    constraint_ids = {
        c["id"] for c in model.get("numeric_constraints", []) if c.get("id")
    }
    constraint_by_id = {
        c["id"]: c for c in model.get("numeric_constraints", []) if c.get("id")
    }
    for i, c in enumerate(model.get("numeric_constraints", [])):
        if not c.get("reason"):
            errs.append(f"numeric_constraints[{i}]: needs a reason")
        for src in as_list(c.get("source")):
            if src not in paths:
                errs.append(
                    f"numeric_constraints[{i}]: source '{src}' is not in the corpus"
                )
        _check_condition_refs(
            f"numeric_constraints[{i}].applies_if",
            c.get("applies_if", True),
            questions,
            known,
            errs,
        )
        for target in c.get("overrides", []) or []:
            if target not in constraint_ids:
                errs.append(
                    f"numeric_constraints[{i}] ({c.get('id', '?')}): overrides "
                    f"'{target}', which is not the id of any numeric_constraint"
                )
                continue
            tgt = constraint_by_id[target]
            # overrides means full replacement, not addition. A constraint
            # sharing the target's exact attribute and applies_if isn't a
            # narrower exception — it's the same population, so overriding
            # discards whatever bound the target had instead of adding to
            # it. This is how a "no lower bound stated" filler constraint
            # silently erases a real corpus-stated maximum for the same
            # people it was meant to protect.
            if c.get("attribute") == tgt.get("attribute") and json.dumps(
                c.get("applies_if"), sort_keys=True
            ) == json.dumps(tgt.get("applies_if"), sort_keys=True):
                errs.append(
                    f"numeric_constraints[{i}] ({c.get('id', '?')}): overrides "
                    f"'{target}', which has the identical applies_if — this "
                    f"discards {target}'s bound rather than narrowing it; "
                    f"merge the two constraints instead"
                )
    if errs:
        return errs  # dynamic results are noise until references resolve

    asked = {q for p in profiles for q in p}
    shown = {
        (q, o)
        for p in profiles
        for q, v in p.items()
        for o in (v if isinstance(v, list) else [v])
    }
    for qid, q in questions.items():
        if qid not in asked:
            errs.append(f"{qid} is never asked: check its ask_if")
            continue
        for o in q["options"]:
            if (qid, o["id"]) not in shown:
                errs.append(f"{qid}.{o['id']} is never shown: check its option_filter")
    for fid in facts:
        values = {str(resolve(model, fid, p)) for p in profiles}
        if len(values) < 2:
            errs.append(f"fact {fid} is always {values.pop()}: it branches nothing")
    first_qid = min(
        (q["id"] for q in model.get("questions", [])),
        key=lambda qid: questions[qid].get("order", 0),
        default=None,
    )
    for attr in model.get("numeric_attributes", []):
        spans = [(p, solve(model, p, attr["id"])) for p in profiles]
        bad = sum(1 for _, s in spans if s["empty"])
        if bad:
            errs.append(
                f"{bad} profile(s) admit no valid {attr['id']}: "
                f"the model permits answers describing nobody"
            )
        # lo=0.0 with no constraint behind it is not a real floor — it is
        # the absence of one, and draw_age would treat it as if a newborn
        # were a legitimate answer. Report which routes have no lower bound
        # at all so a constraint can be added for exactly those routes.
        unfloored = [p for p, s in spans if not s["floored"]]
        if unfloored:
            routes = sorted(
                {str(p.get(first_qid)) for p in unfloored if first_qid in p}
            )
            errs.append(
                f"{len(unfloored)} profile(s) have no lower bound on "
                f"{attr['id']} (nothing in numeric_constraints applies to "
                f"them): {first_qid} = {', '.join(routes) or 'n/a'}"
            )
    return errs


def safe_validate(model, paths, seed):
    """Validate a model, turning a crash while sampling into an error to fix.

    A model using an operator or reference outside the supported subset
    raises instead of failing quietly, so the repair loop needs it as an
    error string rather than a fatal exception.

    Args:
        model: The elicitation model.
        paths: Citable paths, from `load_corpus`.
        seed: Random seed for sampling.

    Returns:
        A tuple of (errors, profiles). profiles is empty if sampling failed.
    """
    try:
        profiles = generate(model, seed=seed)
    except (ValueError, KeyError, TypeError, AttributeError, IndexError) as exc:
        return [f"model is broken: {exc}"], []
    return validate(model, paths, profiles), profiles


# --------------------------------------------------------------------------
# describe and review
# --------------------------------------------------------------------------


def describe(model, answers, rng, today=None):
    """Expand answers into a reviewable record.

    Args:
        model: The elicitation model.
        answers: The profile's answers.
        rng: Seeded random source for numeric attributes.
        today: Date used for date-derived bounds.

    Returns:
        A record with raw answers, their labels, numeric attributes and
        derived facts.
    """
    questions = {q["id"]: q for q in model["questions"]}
    readable = {}
    for qid, v in answers.items():
        q = questions[qid]
        labels = {o["id"]: o["label"] for o in q["options"]}
        readable[q["text"]] = (
            [labels.get(x, x) for x in v] if isinstance(v, list) else labels.get(v, v)
        )
    numeric = {}
    for attr in model.get("numeric_attributes", []):
        span = solve(model, answers, attr["id"], today)
        value = draw_age(rng, span)
        numeric[attr["id"]] = {
            "value": value,
            "unit": attr.get("unit", ""),
            "range": [span["lo"], None if span["hi"] == INF else span["hi"]],
            "floor_because": span["why_lo"],
            "ceiling_because": span["why_hi"],
            "impossible": span["empty"],
            "floored": span["floored"],
        }
    return {
        "answers": answers,
        "readable": readable,
        "numeric": numeric,
        "facts": {
            f["id"]: resolve(model, f["id"], answers) for f in model.get("facts", [])
        },
        "questions_asked": len(answers),
        "questions_skipped": len(model["questions"]) - len(answers),
    }


RUBRIC = """\
You are reviewing a personalised plan generated for a synthetic user.

Judge it against the assertions given, not against your own sense of what a
plan should contain. Mark each met, not_met or unclear, and quote the part of
the plan that decides it. A must_not_reflect assertion fails if the plan
includes the step it denies.

Then check three things assertions cannot cover: are steps in an order this
person could follow; is any step missing that their answers imply; does
anything read as written for a different person.

Report the most damaging problem first. A plan presenting steps someone
cannot legally take is worse than one that is merely incomplete."""


def review_packet(model, record, rarity):
    """Assemble one review packet.

    Assertions are built from facts, not question sources: a question's
    source is the same whichever answer was given, so it says nothing about
    this person, whereas a fact is computed from their answers.

    Args:
        model: The elicitation model.
        record: A described profile record.
        rarity: How often each fact outcome occurs across the set.

    Returns:
        A packet holding the profile, its assertions and risk, plus empty
        slots for the plan and the two verdicts.
    """
    answers = record["answers"]
    claims, score, why = [], 0.0, []

    for f in model.get("facts", []):
        value = resolve(model, f["id"], answers)
        label = f["id"].replace("_", " ")
        if value is not None and value is not False:
            claims.append(
                {
                    "type": "must_reflect",
                    "fact": f["id"],
                    "claim": f"Plan must be consistent with: {label}"
                    f"{'' if value is True else f' = {value}'}",
                    "note": f.get("description", ""),
                    "source": f.get("source", []),
                }
            )
            key = f["id"] if value is True else f"{f['id']}={value}"
            if rarity.get(key, 1.0) < 0.15:
                score += 3
                why.append(f"rare outcome {key} ({rarity.get(key, 0):.0%})")
        elif (
            value is False
            and rarity.get(f["id"], 0.0) >= 0.10
            and fact_reachable(model, f["id"], answers)
        ):
            # A false exemption is as load-bearing as a true one: the step
            # stays in the plan. But only assert it where it could have
            # been true for this kind of person, or the checklist fills
            # with noise and stops being read.
            claims.append(
                {
                    "type": "must_not_reflect",
                    "fact": f["id"],
                    "claim": f"Plan must NOT assume: {label}",
                    "note": f.get("description", ""),
                    "source": f.get("source", []),
                }
            )

    for c in model.get("numeric_constraints", []):
        if c.get("kind") == "eligibility" and ev(
            model, c.get("applies_if", True), answers
        ):
            claims.append(
                {
                    "type": "eligibility",
                    "claim": c.get("reason", ""),
                    "source": c.get("source", []),
                }
            )

    age = record.get("numeric", {}).get("age", {})
    if age.get("impossible"):
        score += 10
        why.append("no valid age: answers describe nobody")
    elif age.get("value") is not None and age["value"] in age.get("range", []):
        score += 3
        why.append("age sits exactly on a legal boundary")
    if record["questions_skipped"] > record["questions_asked"]:
        score += 2
        why.append("most questions skipped — short, easily wrong plan")
    if any(isinstance(v, list) and len(v) > 2 for v in answers.values()):
        score += 2
        why.append("several simultaneous support needs")

    return {
        "review_id": "R"
        + hashlib.sha256(
            json.dumps(signature(model, answers), default=str).encode()
        ).hexdigest()[:10],
        **record,
        "assertions": claims,
        "risk": {"score": round(score, 1), "reasons": why},
        "plan": None,
        "review": {"human": None, "llm": None},
    }


def fact_rarity(model, records):
    """Measure how often each fact outcome occurs.

    Args:
        model: The elicitation model.
        records: Described profile records.

    Returns:
        Frequency by fact id for booleans, or `fact=value` for maps.
    """
    counts = {}
    for r in records:
        for f in model.get("facts", []):
            v = resolve(model, f["id"], r["answers"])
            if v is None or v is False:
                continue
            key = f["id"] if v is True else f"{f['id']}={v}"
            counts[key] = counts.get(key, 0) + 1
    return {k: v / max(len(records), 1) for k, v in counts.items()}


def age_table(model, records):
    """Summarise each numeric attribute by the first question's answer.

    Grouping by the first-asked question is a proxy for "route through the
    questionnaire" — every model fixes this as `q_main_goal`. A route with a
    plausible spread of values looks unremarkable; a route stuck near the
    floor, or with every profile unfloored, stands out at a glance.

    Args:
        model: The elicitation model.
        records: Described profile records (from `describe`).

    Returns:
        A formatted string table, one block per numeric attribute.
    """
    first_qid = min(
        model.get("questions", []), key=lambda q: q.get("order", 0), default=None
    )
    first_qid = first_qid["id"] if first_qid else None
    if not first_qid:
        return ""

    blocks = []
    for attr in model.get("numeric_attributes", []):
        aid = attr["id"]
        by_route = {}
        for r in records:
            route = str(r["answers"].get(first_qid, "n/a"))
            n = r["numeric"].get(aid, {})
            if n.get("value") is None:
                continue
            by_route.setdefault(route, []).append(n)

        lines = [f"{aid} by {first_qid}:"]
        header = (
            f"  {'route':<28}{'n':>4}{'min':>6}{'med':>6}{'max':>6}{'unfloored':>11}"
        )
        lines.append(header)
        for route, ns in sorted(by_route.items()):
            values = [n["value"] for n in ns]
            unfloored = sum(1 for n in ns if not n.get("floored"))
            lines.append(
                f"  {route:<28}{len(ns):>4}{min(values):>6.0f}"
                f"{statistics.median(values):>6.0f}{max(values):>6.0f}"
                f"{unfloored:>11}"
            )
        blocks.append("\n".join(lines))
    return "\n\n".join(blocks)


def persona_budget(n_profiles, cap=40, k=4.0):
    """How many profiles get an LLM-written persona.

    Grows with the square root of profile count, capped, so a model with
    far more genuine branches doesn't scale persona cost linearly with it.

    Args:
        n_profiles: Total profiles found.
        cap: Hard ceiling regardless of n_profiles.
        k: Growth constant multiplying sqrt(n_profiles).

    Returns:
        Number of profiles to generate personas for.
    """
    return min(n_profiles, cap, round(k * math.sqrt(n_profiles)))


# --------------------------------------------------------------------------


def _client(region):
    """Create a Bedrock client lazily, so a pure-compute run needs no boto3."""
    import boto3

    return boto3.client("bedrock-runtime", region_name=region)


def _report(usage, model, records, errors):
    """Print the token, age-table and count summary shared by both commands."""
    if usage:
        print(
            f"total tokens: {usage.get('input', 0)} in / {usage.get('output', 0)} out "
            f"= {usage.get('input', 0) + usage.get('output', 0)}"
        )
    table = age_table(model, records)
    if table:
        print(table)
    print(
        f"{len(model['questions'])} questions, {len(records)} profiles, "
        f"{'clean' if not errors else str(len(errors)) + ' issues'}"
    )


def cmd_model(args):
    """Generate a questionnaire model and a summary for a human to review.

    Runs the repair loop until the model validates, writes it and a Markdown
    summary, then prints the same diagnostics a sampling run would, so the
    reviewer can judge whether the model is viable before amending it.
    """
    life_event, corpus, paths = load_corpus(args.subgraph)
    usage = {}
    client = _client(args.region)
    user = f"Life event: {life_event}\n\n{corpus}"
    model = call(client, SYSTEM, user, TOOL, usage=usage)
    for attempt in range(args.repairs + 1):
        # Full budget, not a cheap sample: a narrow option gated behind two
        # prior answers needs the whole run to appear, and reporting it as
        # dead sends the repair stage chasing a phantom.
        errors, _ = safe_validate(model, paths, args.seed)
        if not errors:
            break
        print(f"validation: {len(errors)} issue(s)", file=sys.stderr)
        for e in errors[:8]:
            print("  " + e, file=sys.stderr)
        if attempt == args.repairs:
            break
        model = call(
            client,
            SYSTEM + "\n\n" + REPAIR,
            f"{user}\n\nModel:\n{json.dumps(model)}\n\nErrors:\n" + "\n".join(errors),
            TOOL,
            usage=usage,
        )
    model["meta"] = {
        "life_event": life_event,
        "validation": "clean" if not errors else f"{len(errors)} unresolved",
    }
    Path(args.out).write_text(json.dumps(model, indent=2))

    errors, profiles = safe_validate(model, paths, args.seed)
    summary_path = args.summary or str(Path(args.out).with_suffix(".md"))
    Path(summary_path).write_text(summarize(model, life_event, profiles))
    rng = random.Random(args.seed)
    records = [
        {"id": f"P{i:03d}", **describe(model, p, rng)}
        for i, p in enumerate(profiles, 1)
    ]
    _report(usage, model, records, errors)
    print(
        f"review {args.out} (summary: {summary_path}), then run: "
        f"plans.py profiles {args.subgraph} --model {args.out}"
    )
    return 1 if errors else 0


def cmd_profiles(args):
    """Sample profiles, personas and review packets from a reviewed model.

    Refuses to sample a model that no longer validates: generation guaranteed a
    clean model, but a hand-amended one may not be, and a broken edit would
    silently degrade every profile, persona and review built from it.
    """
    life_event, _, paths = load_corpus(args.subgraph)
    model = json.loads(Path(args.model).read_text())
    usage = {}

    errors, profiles = safe_validate(model, paths, args.seed)
    if errors:
        print(
            f"validation: {len(errors)} issue(s) — fix the model before sampling",
            file=sys.stderr,
        )
        for e in errors:
            print("  " + e, file=sys.stderr)
        return 1

    rng = random.Random(args.seed)
    records = [
        {"id": f"P{i:03d}", **describe(model, p, rng)}
        for i, p in enumerate(profiles, 1)
    ]

    if args.personas:
        client = _client(args.region)
        # Highest risk first, so a capped budget still covers the profiles
        # most likely to expose a real problem.
        rarity = fact_rarity(model, records)
        by_risk = sorted(
            records, key=lambda r: -review_packet(model, r, rarity)["risk"]["score"]
        )
        for r in by_risk[: persona_budget(len(records))]:
            r["persona"] = call(
                client,
                PERSONA_SYSTEM,
                json.dumps(
                    {"answers": r["readable"], "fixed": r["numeric"]},
                    indent=1,
                    default=str,
                ),
                PERSONA_TOOL,
                max_tokens=2000,
                usage=usage,
            )

    if args.profiles:
        Path(args.profiles).write_text(
            json.dumps(
                {
                    "meta": {"life_event": life_event, "count": len(records)},
                    "profiles": records,
                },
                indent=2,
                default=str,
            )
        )
    if args.review:
        rarity = fact_rarity(model, records)
        packets = sorted(
            (review_packet(model, r, rarity) for r in records),
            key=lambda p: -p["risk"]["score"],
        )
        Path(args.review).write_text(
            json.dumps(
                {
                    "meta": {
                        "life_event": life_event,
                        "count": len(packets),
                        "rubric": RUBRIC,
                        "fact_rarity": rarity,
                    },
                    "packets": packets,
                },
                indent=2,
                default=str,
            )
        )

    _report(usage, model, records, errors)
    return 0


def main(argv=None):
    """Entry point.

    `model` generates a questionnaire and a summary for a human to review;
    `profiles` samples one that has been reviewed and amended.

    Args:
        argv: Argument list, or None to read from sys.argv.

    Returns:
        Exit code; 0 on success, 1 if validation issues remain.
    """
    ap = argparse.ArgumentParser(description=__doc__)
    sub = ap.add_subparsers(dest="command", required=True)

    m = sub.add_parser("model", help="generate a reviewable questionnaire model")
    m.add_argument("subgraph")
    m.add_argument("-o", "--out", default="data/model.json")
    m.add_argument("--summary", help="summary path (default: --out with a .md suffix)")
    m.add_argument("--repairs", type=int, default=3)
    m.add_argument("--seed", type=int, default=0)
    m.add_argument("--region", default="eu-west-2")
    m.set_defaults(func=cmd_model)

    p = sub.add_parser("profiles", help="sample profiles from a reviewed model")
    p.add_argument("subgraph")
    p.add_argument("--model", required=True, help="the reviewed / amended model JSON")
    p.add_argument("--profiles", help="write profile records here")
    p.add_argument("--review", help="write review packets here")
    p.add_argument("--personas", action="store_true")
    p.add_argument("--seed", type=int, default=0)
    p.add_argument("--region", default="eu-west-2")
    p.set_defaults(func=cmd_profiles)

    args = ap.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
