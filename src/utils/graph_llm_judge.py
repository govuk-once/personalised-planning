"""
Script to check service-graph node and edge properties against
the actual GOV.UK page content carried in the knowledge-graph subgraph.

Design
------
Claims are enumerated in Python from fixed field paths (desc, eligibility.*,
financialData.*, agentInteraction.*, contactInfo.*), not by the model. The
model only returns a verdict per claim id. That keeps aggregation stable
across runs and gives per-field accuracy rather than one vague score per node.

One Bedrock call per node (all of that node's claims in a single call, so the
page content is sent once) and one call per source node for its outgoing
edges. Structured output is forced via the Converse API's toolConfig rather
than JSON-in-prose, so no response parsing or repair is needed.

Verdicts
--------
  supported    the page content states this
  contradicted the page content says something different — a real error
  not_stated   the page does not cover it. NOT an error on its own: the claim
               may be sourced from another page or from policy the page does
               not restate. Reported separately for exactly that reason.

Usage
-----
    # Always cost-check first — this sends full page bodies.
    python src/utils/graph_llm_judge.py --kg data/driving_subgraph.json \
        --sg mcp-servers/service-graph/src/service-graph-export.json --life-event driving --dry-run

    python graph_llm_judge.py --kg ... --sg ... --life-event driving \
        --sg-scope dept --dept-keys dvla dvsa --out reports/

    python graph_llm_judge.py ... --tasks nodes --limit 3   # smoke test
"""

from __future__ import annotations

import argparse
import csv
import json
from collections import Counter, defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from bedrock_client import DEFAULT_MODEL_ID, DEFAULT_REGION, BedrockClaude
from graph_match import (
    NodeMatch,
    extract_content_text,
    load_knowledge_graph,
    load_service_graph,
    match_nodes,
    scope_service_graph,
)

VERDICTS = ["supported", "contradicted", "not_stated"]

SYSTEM_PROMPT = """You are auditing a hand-curated UK government service graph \
against the authoritative GOV.UK page content for the same service.

For each claim you are given, decide whether the supplied page content supports it.

- supported: the content states this, or states something that clearly entails it. \
Minor wording differences are fine.
- contradicted: the content states something incompatible — a different figure, \
deadline, age threshold, eligibility rule or process.
- not_stated: the content simply does not address the claim. This is not an error; \
the claim may be sourced from a different page. Do not guess from prior knowledge.
Many claims bundle several assertions into one sentence. Judge the claim as a whole:

- If every part the content addresses is consistent with the claim, return supported, \
even where the content is silent on the remaining parts. Name the unaddressed parts in \
the evidence field.
- Return contradicted only for a direct conflict, where the content asserts something \
that cannot be true at the same time as the claim. Silence is never a contradiction, \
and neither is a difference in wording for the same thing.
- Return not_stated only when the content addresses none of the claim.

Judge only against the supplied content. Never use outside knowledge to mark a claim \
supported or contradicted. Quote the shortest span of the content that decides the \
verdict, and for contradictions state what the content actually says."""


# --------------------------------------------------------------------------
# claim extraction
# --------------------------------------------------------------------------


@dataclass
class Claim:
    claim_id: str
    field: str
    text: str


def _add(claims: list[Claim], field: str, value: Any, index: int | None = None) -> None:
    if value is None or value == "" or value == []:
        return
    text = str(value).strip()
    if not text or text.lower() in {"null", "none", "n/a"}:
        return
    claim_id = f"{field}[{index}]" if index is not None else field
    claims.append(Claim(claim_id=claim_id, field=field, text=text))


def _extract_eligibility_claims(claims: list[Claim], eligibility: dict[str, Any]) -> None:
    _add(claims, "eligibility.summary", eligibility.get("summary"))
    if eligibility.get("universal") is True:
        _add(claims, "eligibility.universal", "This applies to everyone, with no eligibility test.")
    if eligibility.get("means_tested") is True:
        _add(claims, "eligibility.means_tested", "This service is means tested.")

    for index, criterion in enumerate(eligibility.get("criteria") or []):
        _add(
            claims,
            "eligibility.criteria",
            f"{criterion.get('factor')}: {criterion.get('description')}",
            index,
        )
    for key in ("evidenceRequired", "ruleIn", "ruleOut", "exclusions", "autoQualifiers"):
        for index, item in enumerate(eligibility.get(key) or []):
            _add(claims, f"eligibility.{key}", item, index)
    for index, rule in enumerate(eligibility.get("rules") or []):
        _add(claims, "eligibility.rules", rule.get("label"), index)


def _extract_financial_claims(claims: list[Claim], financial: dict[str, Any]) -> None:
    for name, amount in (financial.get("rates") or {}).items():
        _add(claims, "financialData.rates", f"The {name} is £{amount}.", None)
        claims[-1].claim_id = f"financialData.rates.{name}"
    _add(claims, "financialData.frequency", financial.get("frequency"))


def _extract_interaction_claims(claims: list[Claim], interaction: dict[str, Any]) -> None:
    if interaction.get("methods"):
        _add(
            claims,
            "agentInteraction.methods",
            "This service can be used by: " + ", ".join(interaction["methods"]),
        )
    _add(
        claims,
        "agentInteraction.authRequired",
        f"Authentication required to use this service: {interaction.get('authRequired')}"
        if interaction.get("authRequired") not in (None, "none")
        else None,
    )


def extract_claims(sg_node: dict[str, Any]) -> list[Claim]:
    """Enumerate the factually checkable assertions in a service-graph node."""
    claims: list[Claim] = []

    _add(claims, "desc", sg_node.get("desc"))
    _add(claims, "deadline", sg_node.get("deadline"))
    _add(claims, "serviceType", f"This service is best classified as: {sg_node.get('serviceType')}")

    _extract_eligibility_claims(claims, sg_node.get("eligibility") or {})
    _extract_financial_claims(claims, sg_node.get("financialData") or {})
    _extract_interaction_claims(claims, sg_node.get("agentInteraction") or {})

    contact = sg_node.get("contactInfo") or {}
    for key in ("phone", "textphone", "email", "address", "openingHours", "webchat"):
        _add(claims, f"contactInfo.{key}", contact.get(key))

    if sg_node.get("nations"):
        _add(
            claims,
            "nations",
            "This service applies in: " + ", ".join(sg_node["nations"]),
        )
    return claims


# --------------------------------------------------------------------------
# task construction
# --------------------------------------------------------------------------


@dataclass
class NodeTask:
    kind: str
    sg_id: str
    sg_name: str
    kg_path: str
    kg_title: str
    content: str
    claims: list[Claim]


@dataclass
class EdgeTask:
    kind: str
    sg_id: str
    sg_name: str
    kg_path: str
    kg_title: str
    content: str
    edges: list[dict[str, str]]


def build_node_tasks(
    matches: list[NodeMatch],
    knowledge_graph,
    service_graph,
    prefer: str,
    max_chars: int,
    in_scope_only: bool,
) -> tuple[list[NodeTask], list[dict[str, str]]]:
    tasks, skipped = [], []
    for match in matches:
        if in_scope_only and not match.sg_in_scope:
            continue
        sg_node = service_graph.by_id[match.sg_id]
        kg_node = knowledge_graph.by_content_id[match.kg_content_id]
        content = extract_content_text(kg_node.get("details"), prefer=prefer, max_chars=max_chars)
        claims = extract_claims(sg_node)
        if not content.strip():
            skipped.append({"sg_id": match.sg_id, "reason": "no_extractable_page_content"})
            continue
        if not claims:
            skipped.append({"sg_id": match.sg_id, "reason": "no_checkable_claims"})
            continue
        tasks.append(
            NodeTask(
                kind="node",
                sg_id=match.sg_id,
                sg_name=match.sg_name,
                kg_path=match.kg_path,
                kg_title=match.kg_title,
                content=content,
                claims=claims,
            )
        )
    return tasks, skipped


def build_edge_tasks(
    matches: list[NodeMatch],
    knowledge_graph,
    service_graph,
    scope_ids: set[str],
    prefer: str,
    max_chars: int,
) -> tuple[list[EdgeTask], list[dict[str, str]]]:
    """One task per matched source node, carrying all its outgoing in-scope edges."""
    by_source: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for edge in service_graph.edges:
        if edge["from"] in scope_ids and edge["to"] in scope_ids:
            by_source[edge["from"]].append(edge)

    match_by_sg_id = {m.sg_id: m for m in matches}
    tasks, skipped = [], []
    for source_id, edges in by_source.items():
        match = match_by_sg_id.get(source_id)
        if match is None:
            skipped.append({"sg_id": source_id, "reason": "source_not_matched_to_kg"})
            continue
        kg_node = knowledge_graph.by_content_id[match.kg_content_id]
        content = extract_content_text(kg_node.get("details"), prefer=prefer, max_chars=max_chars)
        if not content.strip():
            skipped.append({"sg_id": source_id, "reason": "no_extractable_page_content"})
            continue
        payload = []
        for index, edge in enumerate(edges):
            target = service_graph.by_id[edge["to"]]
            payload.append(
                {
                    "edge_id": f"{source_id}->{edge['to']}",
                    "index": str(index),
                    "target_id": edge["to"],
                    "target_name": target.get("name", ""),
                    "target_path": target.get("base_path") or target.get("govuk_url") or "",
                    "type": edge.get("type", "RELATED"),
                }
            )
        tasks.append(
            EdgeTask(
                kind="edge",
                sg_id=source_id,
                sg_name=match.sg_name,
                kg_path=match.kg_path,
                kg_title=match.kg_title,
                content=content,
                edges=payload,
            )
        )
    return tasks, skipped


# --------------------------------------------------------------------------
# prompts
# --------------------------------------------------------------------------


def node_prompt(task: NodeTask) -> str:
    claim_lines = "\n".join(f'- id="{c.claim_id}": {c.text}' for c in task.claims)
    return f"""Service graph node: {task.sg_name} (id: {task.sg_id})
Authoritative GOV.UK page: {task.kg_title} ({task.kg_path})

CLAIMS TO CHECK
{claim_lines}

GOV.UK PAGE CONTENT
\"\"\"
{task.content}
\"\"\"

Return one verdict for every claim id listed above."""


def edge_prompt(task: EdgeTask) -> str:
    edge_lines = "\n".join(
        f'- id="{e["edge_id"]}": {task.sg_name} --{e["type"]}--> {e["target_name"]} ({e["target_path"]})'
        for e in task.edges
    )
    return f"""The service graph asserts these relationships from "{task.sg_name}".
A RELATED edge means the two services are meaningfully connected for a citizen \
going through this life event. A REQUIRES edge means the target must be completed \
or held before the source can be done.

Authoritative GOV.UK page for the source: {task.kg_title} ({task.kg_path})

RELATIONSHIPS TO CHECK
{edge_lines}

For each, decide whether the source page's content evidences the relationship, and \
whether the asserted type is right. If the content shows a dependency the graph \
labelled RELATED, say so via suggested_type.

GOV.UK PAGE CONTENT
\"\"\"
{task.content}
\"\"\"

Return one verdict for every relationship id listed above."""


NODE_TOOL = {
    "toolSpec": {
        "name": "record_claim_verdicts",
        "description": "Record a verdict for every claim.",
        "inputSchema": {
            "json": {
                "type": "object",
                "properties": {
                    "verdicts": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "claim_id": {"type": "string"},
                                "verdict": {"type": "string", "enum": VERDICTS},
                                "evidence": {
                                    "type": "string",
                                    "description": "Shortest span of page content deciding the verdict; empty if not_stated.",
                                },
                                "correction": {
                                    "type": "string",
                                    "description": "What the page actually says. Only for contradicted.",
                                },
                            },
                            "required": ["claim_id", "verdict"],
                        },
                    }
                },
                "required": ["verdicts"],
            }
        },
    }
}

EDGE_TOOL = {
    "toolSpec": {
        "name": "record_edge_verdicts",
        "description": "Record a verdict for every asserted relationship.",
        "inputSchema": {
            "json": {
                "type": "object",
                "properties": {
                    "verdicts": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "edge_id": {"type": "string"},
                                "verdict": {"type": "string", "enum": VERDICTS},
                                "suggested_type": {
                                    "type": "string",
                                    "enum": ["REQUIRES", "RELATED", "NONE"],
                                },
                                "evidence": {"type": "string"},
                            },
                            "required": ["edge_id", "verdict"],
                        },
                    }
                },
                "required": ["verdicts"],
            }
        },
    }
}


# --------------------------------------------------------------------------
# Bedrock
# --------------------------------------------------------------------------


# --------------------------------------------------------------------------
# execution
# --------------------------------------------------------------------------


def run_node_task(judge: BedrockClaude, task: NodeTask) -> list[dict[str, Any]]:
    result, usage = judge.converse_structured(node_prompt(task), NODE_TOOL, system=SYSTEM_PROMPT)
    by_id = {c.claim_id: c for c in task.claims}
    returned = {v.get("claim_id"): v for v in result.get("verdicts", [])}

    rows = []
    for position, claim in enumerate(task.claims):
        verdict = returned.get(claim.claim_id, {})
        rows.append(
            {
                "kind": "node",
                "sg_id": task.sg_id,
                "sg_name": task.sg_name,
                "kg_path": task.kg_path,
                "claim_id": claim.claim_id,
                "field": claim.field,
                "claim": claim.text,
                "verdict": verdict.get("verdict", "missing_response"),
                "evidence": (verdict.get("evidence") or "")[:400],
                "correction": (verdict.get("correction") or "")[:400],
                "input_tokens": usage.get("inputTokens", 0) if position == 0 else 0,
                "output_tokens": usage.get("outputTokens", 0) if position == 0 else 0,
            }
        )
    for claim_id in set(returned) - set(by_id):
        rows.append(
            {
                "kind": "node",
                "sg_id": task.sg_id,
                "sg_name": task.sg_name,
                "kg_path": task.kg_path,
                "claim_id": claim_id,
                "field": "UNKNOWN",
                "claim": "",
                "verdict": "hallucinated_claim_id",
                "evidence": "",
                "correction": "",
                "input_tokens": 0,
                "output_tokens": 0,
            }
        )
    return rows


def run_edge_task(judge: BedrockClaude, task: EdgeTask) -> list[dict[str, Any]]:
    result, usage = judge.converse_structured(edge_prompt(task), EDGE_TOOL, system=SYSTEM_PROMPT)
    returned = {v.get("edge_id"): v for v in result.get("verdicts", [])}

    rows = []
    for position, edge in enumerate(task.edges):
        verdict = returned.get(edge["edge_id"], {})
        rows.append(
            {
                "kind": "edge",
                "sg_id": task.sg_id,
                "sg_name": task.sg_name,
                "kg_path": task.kg_path,
                "claim_id": edge["edge_id"],
                "field": f"edge:{edge['type']}",
                "claim": f"{task.sg_name} --{edge['type']}--> {edge['target_name']}",
                "verdict": verdict.get("verdict", "missing_response"),
                "evidence": (verdict.get("evidence") or "")[:400],
                "correction": (
                    ""
                    if verdict.get("suggested_type", edge["type"]) == edge["type"]
                    else f"suggested_type={verdict.get('suggested_type')}"
                ),
                "input_tokens": usage.get("inputTokens", 0) if position == 0 else 0,
                "output_tokens": usage.get("outputTokens", 0) if position == 0 else 0,
            }
        )
    return rows


def summarise(rows: list[dict[str, Any]]) -> dict[str, Any]:
    def block(subset: list[dict[str, Any]]) -> dict[str, Any]:
        counts = Counter(r["verdict"] for r in subset)
        decided = counts["supported"] + counts["contradicted"]
        return {
            "total": len(subset),
            "verdicts": dict(counts),
            # Accuracy over claims the page actually addresses. not_stated is
            # excluded from the denominator: it means "unverifiable here", not
            # "wrong". Track it via coverage instead.
            "accuracy_where_decidable": round(counts["supported"] / decided, 4)
            if decided
            else None,
            "coverage": round(decided / len(subset), 4) if subset else None,
        }

    node_rows = [r for r in rows if r["kind"] == "node"]
    edge_rows = [r for r in rows if r["kind"] == "edge"]

    by_field: dict[str, Any] = {}
    for field in sorted({r["field"] for r in node_rows}):
        by_field[field] = block([r for r in node_rows if r["field"] == field])

    by_node: dict[str, Any] = {}
    for sg_id in sorted({r["sg_id"] for r in node_rows}):
        by_node[sg_id] = block([r for r in node_rows if r["sg_id"] == sg_id])

    return {
        "overall_nodes": block(node_rows),
        "overall_edges": block(edge_rows),
        "by_field": by_field,
        "by_node": by_node,
        "total_input_tokens": sum(r["input_tokens"] for r in rows),
        "total_output_tokens": sum(r["output_tokens"] for r in rows),
        "contradictions": [
            {
                "sg_id": r["sg_id"],
                "claim_id": r["claim_id"],
                "claim": r["claim"],
                "correction": r["correction"],
                "evidence": r["evidence"],
            }
            for r in rows
            if r["verdict"] == "contradicted"
        ],
    }


def _dry_run_report(
    tasks: list[Any],
    life_event: str,
    num_matches: int,
    num_scope_ids: int,
    sg_scope: str,
    skipped: list[dict[str, str]],
) -> None:
    prompts = [node_prompt(t) if t.kind == "node" else edge_prompt(t) for t in tasks]
    chars = sum(len(p) for p in prompts) + len(SYSTEM_PROMPT) * len(prompts)
    units = sum(len(t.claims) if t.kind == "node" else len(t.edges) for t in tasks)
    print(f"\nlife event      : {life_event} (scope: {sg_scope}, {num_scope_ids} nodes)")
    print(f"matched nodes   : {num_matches}")
    print(
        f"tasks           : {len(tasks)} "
        f"({sum(1 for t in tasks if t.kind == 'node')} node, "
        f"{sum(1 for t in tasks if t.kind == 'edge')} edge)"
    )
    print(f"claims / edges  : {units}")
    print(f"prompt chars    : {chars:,}")
    print(f"est. input tok  : ~{chars // 4:,}  (rough 4 chars/token)")
    print(f"skipped         : {Counter(s['reason'] for s in skipped)}")
    print("\nLargest prompts:")
    pairs = sorted(zip(prompts, tasks, strict=True), key=lambda p: -len(p[0]))
    for prompt, task in pairs[:5]:
        print(f"  {len(prompt):>8,} chars  {task.kind:<5} {task.sg_id}")
    print("\nDry run — nothing sent to Bedrock.\n")


def _run_tasks(
    tasks: list[Any],
    judge: BedrockClaude,
    jsonl_path: Path,
    concurrency: int,
) -> tuple[list[dict[str, Any]], list[dict[str, str]]]:
    rows: list[dict[str, Any]] = []
    errors: list[dict[str, str]] = []
    with jsonl_path.open("a") as sink, ThreadPoolExecutor(max_workers=concurrency) as pool:
        futures = {
            pool.submit(
                run_node_task if task.kind == "node" else run_edge_task,
                judge,
                task,
            ): task
            for task in tasks
        }
        for index, future in enumerate(as_completed(futures), start=1):
            task = futures[future]
            try:
                task_rows = future.result()
                rows.extend(task_rows)
                for row in task_rows:
                    sink.write(json.dumps(row) + "\n")
                sink.flush()
                print(f"[{index}/{len(tasks)}] {task.kind} {task.sg_id}")
            except Exception as error:  # noqa: BLE001
                errors.append({"sg_id": task.sg_id, "kind": task.kind, "error": str(error)})
                print(f"[{index}/{len(tasks)}] FAILED {task.sg_id}: {error}")
    return rows, errors


def _write_results(
    rows: list[dict[str, Any]],
    errors: list[dict[str, str]],
    skipped: list[dict[str, str]],
    out_dir: Path,
    life_event: str,
    model_id: str,
) -> None:
    summary = summarise(rows)
    summary["errors"] = errors
    summary["skipped"] = skipped
    summary["model_id"] = model_id
    summary["life_event"] = life_event

    with (out_dir / f"{life_event}_judgements.csv").open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0].keys()) if rows else ["verdict"])
        writer.writeheader()
        writer.writerows(rows)
    (out_dir / f"{life_event}_judge_summary.json").write_text(json.dumps(summary, indent=2))

    print("\n" + "=" * 60)
    print(f"nodes  {summary['overall_nodes']}")
    print(f"edges  {summary['overall_edges']}")
    print(f"tokens in/out  {summary['total_input_tokens']:,} / {summary['total_output_tokens']:,}")
    print(f"contradictions {len(summary['contradictions'])}")
    for item in summary["contradictions"][:10]:
        print(f"  {item['sg_id']} :: {item['claim_id']}")
        print(f"      claim : {item['claim'][:110]}")
        print(f"      page  : {(item['correction'] or item['evidence'])[:110]}")
    print(f"\nWrote judgements to {out_dir}/\n")


def main() -> None:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--kg", required=True)
    parser.add_argument("--sg", required=True)
    parser.add_argument("--life-event", default=None)
    parser.add_argument("--sg-scope", choices=["life_event", "dept", "all"], default="life_event")
    parser.add_argument("--dept-keys", nargs="*", default=["dvla", "dvsa"])
    parser.add_argument("--tasks", choices=["nodes", "edges", "both"], default="both")
    parser.add_argument(
        "--any-scope",
        action="store_true",
        help="judge every matched node, not just those inside the life-event scope",
    )
    parser.add_argument("--model-id", default=DEFAULT_MODEL_ID)
    parser.add_argument("--region", default=DEFAULT_REGION)
    parser.add_argument("--profile", default=None, help="AWS profile name")
    parser.add_argument("--content-format", choices=["govspeak", "html"], default="govspeak")
    parser.add_argument("--max-content-chars", type=int, default=40000)
    parser.add_argument("--limit", type=int, default=None, help="cap number of tasks")
    parser.add_argument("--concurrency", type=int, default=4)
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="print task and token estimates, call nothing, write nothing",
    )
    parser.add_argument(
        "--resume",
        action="store_true",
        help="skip tasks already present in the existing judgements.jsonl",
    )
    parser.add_argument("--out", default="reports")
    args = parser.parse_args()

    knowledge_graph = load_knowledge_graph(args.kg)
    service_graph = load_service_graph(args.sg)
    life_event = args.life_event or knowledge_graph.life_event

    scope_ids = scope_service_graph(
        service_graph,
        mode=args.sg_scope,
        life_event_id=life_event,
        dept_keys=args.dept_keys,
    )
    matches, _, _ = match_nodes(knowledge_graph, service_graph, scope_ids)

    tasks: list[Any] = []
    skipped: list[dict[str, str]] = []
    if args.tasks in ("nodes", "both"):
        node_tasks, node_skipped = build_node_tasks(
            matches,
            knowledge_graph,
            service_graph,
            args.content_format,
            args.max_content_chars,
            in_scope_only=not args.any_scope,
        )
        tasks += node_tasks
        skipped += node_skipped
    if args.tasks in ("edges", "both"):
        edge_tasks, edge_skipped = build_edge_tasks(
            matches,
            knowledge_graph,
            service_graph,
            scope_ids,
            args.content_format,
            args.max_content_chars,
        )
        tasks += edge_tasks
        skipped += edge_skipped

    if args.limit:
        tasks = tasks[: args.limit]

    if args.dry_run:
        _dry_run_report(tasks, life_event, len(matches), len(scope_ids), args.sg_scope, skipped)
        return

    out_dir = Path(args.out).resolve()
    allowed_root = Path.cwd().resolve()
    if not out_dir.is_relative_to(allowed_root):
        raise SystemExit(
            f"Output directory {out_dir} is outside the working directory {allowed_root}"
        )
    out_dir.mkdir(parents=True, exist_ok=True)
    jsonl_path = out_dir / f"{life_event}_judgements.jsonl"

    rows: list[dict[str, Any]] = []
    if args.resume and jsonl_path.exists():
        rows = [json.loads(line) for line in jsonl_path.read_text().splitlines() if line.strip()]
        done = {(r["kind"], r["sg_id"]) for r in rows}
        before = len(tasks)
        tasks = [t for t in tasks if (t.kind, t.sg_id) not in done]
        print(f"Resuming: {len(done)} tasks already judged, {before - len(tasks)} skipped")
    elif jsonl_path.exists():
        jsonl_path.unlink()

    judge = BedrockClaude(model_id=args.model_id, region=args.region, profile=args.profile)
    new_rows, errors = _run_tasks(tasks, judge, jsonl_path, args.concurrency)
    rows.extend(new_rows)
    _write_results(rows, errors, skipped, out_dir, life_event, args.model_id)


if __name__ == "__main__":
    main()
