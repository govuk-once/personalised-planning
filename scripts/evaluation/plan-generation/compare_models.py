r"""Compare questionnaire models from several `plans.py model` runs.

Built for the main-goal experiment: did the model, left free to choose its
opening questions, find the same splits as the graph analysis
(docs/having-a-baby-subgraph-analysis.md)? For each run it reports the
opening questions everyone is asked, which content clusters the model cites,
and which clusters sit under each opening question's branch.

Cluster labels come from a subgraph whose nodes carry a `cluster` field
(e.g. data/having_a_baby_subgraph_pruned.json). The labels are only read
here, never shown to the generating model. Nothing in this script is specific
to one life event: the clusters reported in their own columns ("main
clusters") are the largest ones in the subgraph, or the ones named with
--clusters; every other cluster is counted together as "other".

  python compare_models.py runs/*/model.json \
      --subgraph ../../../data/having_a_baby_subgraph_pruned.json \
      -o runs/comparison.md

  # choose the main clusters by name instead of by size
  python compare_models.py runs/*/model.json --subgraph SUBGRAPH \
      --clusters childcare,work_leave_pay
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from collections import Counter
from pathlib import Path

from plans import as_list, fact_refs, refs

UNLABELLED = "unlabelled"

# Heuristic tags for the dimensions the graph analysis proposed. They only
# help a reader scan the table; check the question text before relying on one.
DIMENSIONS = {
    "nation": r"\b(scotland|wales|northern ireland|england|nation|where do you live)\b",
    "employment": r"\b(employ\w*|self-employed|work(?:ing)?|job|earn\w*|statutory)\b",
    "benefits_income": r"\b(universal credit|benefits?|tax credits?|income|£\d)",
    "stage": r"\b(pregnan\w*|due|born|weeks|age|aged|old)\b",
    "disability": r"\b(disab\w*|neonatal|hospital|special educational)\b",
    "service_choice": r"\b(what do you (?:need|want)|which of these|what would you like)\b",
}


def load_clusters(path: str) -> tuple[dict[str, str], Counter]:
    """Map each base_path to its cluster, and count pages per cluster."""
    graph = json.loads(Path(path).read_text())
    by_path = {n["base_path"]: n.get("cluster", UNLABELLED) for n in graph["nodes"]}
    return by_path, Counter(by_path.values())


def main_clusters(sizes: Counter, names: str | None, top: int) -> tuple[str, ...]:
    """The clusters reported in their own columns.

    Args:
        sizes: Pages per cluster, from `load_clusters`.
        names: Comma-separated cluster names to use, in this order, or None.
        top: Without `names`, how many of the largest labelled clusters to
            use. Ties break by name, so the choice is stable across runs.

    Returns:
        Cluster names, in report column order.

    Raises:
        ValueError: If a named cluster is not in the subgraph.
    """
    if names:
        chosen = tuple(n.strip() for n in names.split(",") if n.strip())
        if unknown := [c for c in chosen if c not in sizes]:
            raise ValueError(
                f"unknown cluster(s) {', '.join(unknown)}; "
                f"the subgraph has {', '.join(sorted(sizes))}"
            )
        return chosen
    labelled = [c for c in sizes if c != UNLABELLED]
    return tuple(sorted(labelled, key=lambda c: (-sizes[c], c))[:top])


def page_of(source: str, by_path: dict[str, str]) -> str | None:
    """Resolve a cited source (possibly `/page/part-slug`) to its base_path."""
    if source in by_path:
        return source
    parent = source.rsplit("/", 1)[0]
    return parent if parent in by_path else None


def is_universal(q: dict) -> bool:
    """True if the question is asked of everyone."""
    return q.get("ask_if", True) is True


def condition_questions(model: dict, cond) -> set[str]:
    """Question ids a condition reads, directly or through facts."""
    questions = {q["id"] for q in model.get("questions", [])}
    facts = {f["id"] for f in model.get("facts", [])}
    found = []
    refs(cond if cond is not True else {}, found)
    out = set()
    for ref, _ in found:
        if ref in questions:
            out.add(ref)
        elif ref in facts:
            out |= fact_refs(model, ref)
    return out


def downstream(model: dict, root: str) -> tuple[set[str], set[str]]:
    """Questions and facts that depend on `root`, transitively.

    A question depends on `root` if its ask_if reads `root` or a question
    that itself depends on it; a fact depends on it if its value reads any of
    those questions.
    """
    deps = {
        q["id"]: condition_questions(model, q.get("ask_if", True))
        for q in model.get("questions", [])
    }
    reached = {root}
    changed = True
    while changed:
        changed = False
        for qid, reads in deps.items():
            if qid not in reached and reads & reached:
                reached.add(qid)
                changed = True
    facts = {
        f["id"] for f in model.get("facts", []) if fact_refs(model, f["id"]) & reached
    }
    return reached - {root}, facts


def cited_clusters(model: dict, qids, fids, by_path) -> Counter:
    """Distinct pages cited by the given questions and facts, per cluster."""
    items = [q for q in model.get("questions", []) if q["id"] in qids]
    items += [f for f in model.get("facts", []) if f["id"] in fids]
    pages = {page_of(s, by_path) for item in items for s in as_list(item.get("source"))}
    pages.discard(None)
    return Counter(by_path[p] for p in pages)


def tags(q: dict) -> list[str]:
    """Heuristic dimension tags for a question, from its text and options."""
    text = " ".join(
        [q.get("text", "")] + [o.get("label", "") for o in q.get("options", [])]
    )
    return [d for d, pat in DIMENSIONS.items() if re.search(pat, text, re.I)]


def run_label(path: Path) -> str:
    """Short label for a run: its folder name, or file stem."""
    return path.parent.name if path.name == "model.json" else path.stem


def analyse(path: Path, by_path, sizes, main, opening: int) -> dict:
    """Everything the comparison reports for one run."""
    model = json.loads(path.read_text())
    meta = model.get("meta", {})
    qs = sorted(model.get("questions", []), key=lambda q: q.get("order", 0))
    all_q = {q["id"] for q in qs}
    all_f = {f["id"] for f in model.get("facts", [])}
    coverage = cited_clusters(model, all_q, all_f, by_path)
    uni = [q for q in qs if is_universal(q)][:opening]
    branches = []
    for q in uni:
        dq, df = downstream(model, q["id"])
        branches.append(
            {
                "q": q,
                "tags": tags(q),
                "n_downstream": len(dq),
                "clusters": cited_clusters(model, dq | {q["id"]}, df, by_path),
            }
        )
    goal = next((q for q in qs if q["id"] == "q_main_goal"), None)
    return {
        "label": run_label(path),
        "path": str(path),
        "meta": meta,
        "n_questions": len(qs),
        "n_facts": len(all_f),
        "n_universal": sum(is_universal(q) for q in qs),
        "goal_rank": qs.index(goal) + 1 if goal else None,
        "coverage": coverage,
        "main_covered": sum(1 for c in main if coverage[c]),
        "opening": branches,
        "questions": qs,
        "sizes": sizes,
        "main": main,
    }


def fmt_clusters(counter: Counter, sizes: Counter, main) -> str:
    """`cluster pages/size` for the main clusters cited, plus any others."""
    parts = [f"{c} {counter[c]}/{sizes[c]}" for c in main if counter[c]]
    other = sum(v for c, v in counter.items() if c not in main)
    if other:
        parts.append(f"other {other}")
    return ", ".join(parts) or "—"


def clean(text: str, n: int = 70) -> str:
    """One-line, table-safe, truncated text."""
    text = re.sub(r"\s+", " ", text).replace("|", "/")
    return text if len(text) <= n else text[: n - 1] + "…"


def render(runs: list[dict]) -> str:
    """Markdown report: one overview table, then a section per run."""
    sizes = runs[0]["sizes"]
    main = runs[0]["main"]
    out = ["# Model comparison", ""]
    out.append(
        "Opening questions are the lowest-order questions asked of everyone. "
        "Dimension tags are keyword heuristics. Cluster cells show "
        "`pages cited / pages in cluster`."
    )
    out += ["", "## Overview", ""]
    out.append(
        "| run | main goal | shuffle | validation | Qs (universal) | facts "
        "| q_main_goal rank | main clusters cited | opening questions (tags) |"
    )
    out.append("|---|---|---|---|---|---|---|---|---|")
    for r in runs:
        m = r["meta"]
        opening = "<br>".join(
            f"{i}. `{b['q']['id']}` ({', '.join(b['tags']) or '—'})"
            for i, b in enumerate(r["opening"], 1)
        )
        out.append(
            f"| {r['label']} | {m.get('main_goal', 'required?')} "
            f"| {m.get('shuffle_seed', '—')} | {m.get('validation', '?')} "
            f"| {r['n_questions']} ({r['n_universal']}) | {r['n_facts']} "
            f"| {r['goal_rank'] or '—'} | {r['main_covered']}/{len(main)} "
            f"| {opening} |"
        )
    out += ["", "## Cluster coverage", ""]
    out.append("| run | " + " | ".join(main) + " | other |")
    out.append("|---|" + "---|" * (len(main) + 1))
    for r in runs:
        cov = r["coverage"]
        other = sum(v for c, v in cov.items() if c not in main)
        out.append(
            f"| {r['label']} | "
            + " | ".join(f"{cov[c]}/{sizes[c]}" for c in main)
            + f" | {other} |"
        )
    for r in runs:
        m = r["meta"]
        out += ["", f"## {r['label']}", ""]
        out.append(
            f"`{r['path']}` — corpus {m.get('corpus', '?')}, "
            f"{m.get('corpus_chars', '?')} chars, page cap {m.get('max_page_chars')}, "
            f"subgraph `{m.get('subgraph', '?')}`"
        )
        out += [
            "",
            "| # | question | options | tags | depends on it | clusters under it |",
            "|---|---|---|---|---|---|",
        ]
        for i, b in enumerate(r["opening"], 1):
            q = b["q"]
            opts = "; ".join(
                clean(o.get("label", o["id"]), 30) for o in q.get("options", [])
            )
            out.append(
                f"| {i} | `{q['id']}`: {clean(q.get('text', ''))} | {clean(opts, 120)} "
                f"| {', '.join(b['tags']) or '—'} | {b['n_downstream']} Qs "
                f"| {fmt_clusters(b['clusters'], sizes, main)} |"
            )
        out += ["", "All questions:", ""]
        out += [
            "| order | question | asked of | rationale |",
            "|---|---|---|---|",
        ]
        for q in r["questions"]:
            out.append(
                f"| {q.get('order', 0)} | `{q['id']}`: {clean(q.get('text', ''), 90)} "
                f"| {asked_of(q)} | {clean(q.get('rationale', '') or '—', 220)} |"
            )
    return "\n".join(out) + "\n"


def asked_of(q: dict) -> str:
    """'everyone', or the questions the ask_if reads, compactly."""
    cond = q.get("ask_if", True)
    if cond is True:
        return "everyone"
    found = []
    refs(cond, found)
    readable = sorted({str(ref) for ref, _ in found if ref})
    return "if " + ", ".join(f"`{r}`" for r in readable) if readable else "conditional"


def main(argv=None) -> int:
    """Entry point."""
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("models", nargs="+", help="model.json files from plans.py model")
    ap.add_argument("--subgraph", required=True, help="subgraph with `cluster` labels")
    ap.add_argument("--opening", type=int, default=5, help="opening questions to show")
    ap.add_argument(
        "--clusters",
        help="comma-separated clusters to report in their own columns "
        "(default: the --top largest in the subgraph)",
    )
    ap.add_argument(
        "--top",
        type=int,
        default=5,
        help="without --clusters, how many of the largest clusters to report (default 5)",
    )
    ap.add_argument("-o", "--out", help="write the report here (default: stdout)")
    args = ap.parse_args(argv)

    by_path, sizes = load_clusters(args.subgraph)
    if set(sizes) == {UNLABELLED}:
        print(
            f"warning: {args.subgraph} has no `cluster` labels; "
            "cluster columns will be empty",
            file=sys.stderr,
        )
    try:
        main = main_clusters(sizes, args.clusters, args.top)
    except ValueError as exc:
        ap.error(str(exc))
    runs = [analyse(Path(p), by_path, sizes, main, args.opening) for p in args.models]
    report = render(runs)
    if args.out:
        Path(args.out).write_text(report)
        print(f"wrote {args.out}")
    else:
        print(report)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
