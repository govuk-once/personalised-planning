"""Render an elicitation model as reviewable Markdown, with a Mermaid diagram.

Kept separate from `plans.py` so the pipeline stays free of presentation code.
`plans.py cmd_model` calls `summarize` to write the `.md` a human reviews before
amending the model. `refs` and `as_list` are imported from `plans` lazily,
inside the functions, because `plans` imports this module at load time and a
top-level import back would be circular.
"""

from __future__ import annotations

import json
import re


def branching(model, profiles=None):
    """Render the question dependency tree as a Mermaid flowchart.

    Each question is a node; an edge runs from the deepest prior question its
    `ask_if` reads to the question it gates, labelled with the answer that
    unlocks it. Using the deepest prerequisite (highest `order`) as the parent
    keeps the chart a tree whose depth mirrors gating depth — a shallower
    condition is implied because the parent is itself gated on it. When
    `profiles` is given, node labels carry the reach count and questions no
    profile ever reaches are flagged, since a precluded branch is the thing a
    reviewer most needs to see.

    Args:
        model: The elicitation model.
        profiles: Sampled answer sets, or None to draw structure only.

    Returns:
        A Markdown block (a fenced ```mermaid diagram plus a reach table), or ""
        if the model has no questions.
    """
    from plans import refs

    qs = {q["id"]: q for q in model.get("questions", [])}
    if not qs:
        return ""
    ordered = sorted(qs.values(), key=lambda q: q.get("order", 0))
    total = len(profiles) if profiles else 0
    reach = (
        {qid: sum(1 for p in profiles if qid in p) for qid in qs} if profiles else {}
    )

    def label(qid, val):
        if not isinstance(qid, str):
            return str(val)
        for o in qs.get(qid, {}).get("options", []):
            if o["id"] == val:
                return o.get("label", val)
        return str(val)

    def clean(text, limit):
        return re.sub(r"\s+", " ", str(text)).replace('"', "").replace("|", "/")[:limit]

    def gloss(node):
        try:
            if node is True:
                return "always"
            if not isinstance(node, dict) or not node:
                return "never"
            op, a = next(iter(node.items()))
            if op in ("and", "or"):
                return f" {op} ".join(gloss(x) for x in a)
            if op == "not":
                return f"not ({gloss(a[0])})"
            if op in ("==", "!="):
                return f"{a[0]} {'=' if op == '==' else '≠'} {label(a[0], a[1])}"
            if op == "in":
                vals = a[1] if isinstance(a[1], list) else list(a[1])
                return f"{a[0]} in [{', '.join(label(a[0], v) for v in vals)}]"
            if op == "any_option_has":
                return f"{a[0]} has an option flagged '{a[1]}'"
            if op == ">=":
                return f"{a[0]} ≥ {a[1]}"
        except (TypeError, IndexError, KeyError):
            pass
        return json.dumps(node, default=str)

    def parent(q):
        found = []
        refs(q.get("ask_if", True), found)
        bylit = {}
        for ref, lit in found:
            if ref in qs:
                bylit.setdefault(ref, []).append(lit)
        if not bylit:
            return None, ""
        pid = max(bylit, key=lambda r: qs[r].get("order", 0))
        lits = [label(pid, x) for x in bylit[pid] if isinstance(x, str)]
        # Edge labels sit between unquoted `|...|`, so a truncated bracket
        # (e.g. "Outside London (") would break the Mermaid parse — strip them.
        return pid, clean(re.sub(r"[()\[\]{}]", "", ", ".join(lits)), 24)

    nodes, edges, dead = [], [], []
    for q in ordered:
        tail = f" ({reach[q['id']]})" if profiles else ""
        nodes.append(
            f'  {q["id"]}["{q.get("order", 0)}. {clean(q.get("text", q["id"]), 44)}{tail}"]'
        )
        if profiles and not reach[q["id"]]:
            dead.append(q["id"])
        pid, lab = parent(q)
        if pid:
            edges.append(f"  {pid} -->{f'|{lab}| ' if lab else ' '}{q['id']}")

    lines = ["## Branching", "", "```mermaid", "flowchart TD", *nodes, *edges]
    if dead:
        lines += [
            "  classDef dead fill:#fdd,stroke:#c00;",
            f"  class {','.join(dead)} dead;",
        ]
    lines.append("```")

    if profiles:
        lines += [
            "",
            f"Reach = how many of {total} sampled profiles are asked each question.",
            "",
            "| # | question | reach | asked when |",
            "|---|---|---|---|",
        ]
        for q in ordered:
            n = reach[q["id"]]
            note = " ⚠ never asked" if not n else ""
            lines.append(
                f"| {q.get('order', 0)} | `{q['id']}` | {n} ({n / total:.0%}){note} "
                f"| {gloss(q.get('ask_if', True))} |"
            )
    return "\n".join(lines) + "\n"


def summarize(model, life_event, profiles=None):
    """Render a model as Markdown for a human to review before amending.

    Opens with the branching diagram (see `branching`) so the reviewer sees
    which questions preclude others and how profiles distribute across them,
    then lists every collection in full. Conditions in those lists are shown as
    compact JSON, not prose: the reviewer edits the JSON model, so the exact
    JsonLogic is more useful than a paraphrase and avoids a second interpreter
    that could drift from `ev`.

    Args:
        model: The elicitation model.
        life_event: The life event the model covers.
        profiles: Sampled answer sets for reach counts, or None.

    Returns:
        A Markdown string: branching, then questions, facts, filters, constraints.
    """
    from plans import as_list

    def j(n):
        return json.dumps(n, default=str)

    def src(o):
        return (
            f" — _source:_ {', '.join(as_list(o.get('source')))}"
            if o.get("source")
            else ""
        )

    out = [f"# {life_event} — elicitation model", ""]

    branch = branching(model, profiles)
    if branch:
        out.append(branch)

    out.append("## Questions")
    for q in sorted(model.get("questions", []), key=lambda q: q.get("order", 0)):
        cond = "" if q.get("ask_if", True) is True else f" — ask_if `{j(q['ask_if'])}`"
        out.append(
            f"### {q.get('order', 0)}. {q['id']} ({q.get('type', '?')}){cond}{src(q)}"
        )
        out.append(q.get("text", ""))
        out += [
            f"- `{o['id']}` {o.get('label', '')}"
            f"{' _(' + ', '.join(k for k in o if k not in ('id', 'label')) + ')_' if len(o) > 2 else ''}"
            for o in q.get("options", [])
        ]

    filters = [f for f in model.get("option_filters", []) if isinstance(f, dict)]
    if filters:
        out.append("\n## Option filters")
        out += [
            f"- `{f.get('question_id')}.{f.get('option_id')}` shown_if `{j(f.get('show_if', True))}`"
            for f in filters
        ]

    facts = [f for f in model.get("facts", []) if isinstance(f, dict)]
    if facts:
        out.append("\n## Facts")
        for f in facts:
            body = (
                f"map from `{f.get('from')}`: `{j(f.get('values', {}))}`"
                if f.get("type") == "map"
                else f"`{j(f.get('value', False))}`"
            )
            out.append(f"- **{f['id']}** {f.get('description', '')} = {body}{src(f)}")

    attrs = [a for a in model.get("numeric_attributes", []) if isinstance(a, dict)]
    constraints = [
        c for c in model.get("numeric_constraints", []) if isinstance(c, dict)
    ]
    if attrs or constraints:
        out.append("\n## Numeric attributes & constraints")
        out += [
            f"- **{a['id']}** ({a.get('unit', '')}): {a.get('description', '')}"
            for a in attrs
        ]
        for c in constraints:
            bounds = " ".join(f"{k}={j(c[k])}" for k in ("min", "max") if k in c)
            gate = (
                ""
                if c.get("applies_if", True) is True
                else f" applies_if `{j(c['applies_if'])}`"
            )
            ovr = (
                f" overrides {', '.join(c['overrides'])}" if c.get("overrides") else ""
            )
            out.append(
                f"- `{c.get('id', '?')}` [{c.get('kind', 'eligibility')}] "
                f"{c.get('attribute', '?')} {bounds}{gate}{ovr} — {c.get('reason', '')}{src(c)}"
            )

    return "\n".join(out) + "\n"
