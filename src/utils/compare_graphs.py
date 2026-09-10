"""
This script performs deterministic node and edge completeness comparison between the
GOV.UK knowledge-graph subgraph and the hand-curated service-graph.

What it measures
----------------
Node completeness, split three ways:

  matched_in_scope     KG node exists in the service graph AND is reachable
                       from this life event's entryNodes.
  matched_out_of_scope KG node exists in the service graph but this life event
                       cannot reach it — a wiring gap, not a content gap.
  missing              No service-graph node for this page at all.

Edge completeness is only computed over node pairs where both endpoints
matched.

Usage
-----
    python compare_graphs.py \
        --kg data/driving_subgraph.json \
        --sg mcp-servers/service-graph/src/service-graph-export.json \
        --life-event driving \
        --out data/

    # Widen the service-graph scope to every DVLA/DVSA node, to separate
    # "not modelled" from "modelled but not wired into this life event":
    python compare_graphs.py ... --sg-scope dept --dept-keys dvla dvsa

    # Include /done/ feedback pages and news stories in the denominator:
    python compare_graphs.py ... --keep-noise
"""

from __future__ import annotations

import argparse
import csv
import json
from collections import Counter
from pathlib import Path
from typing import Any

from graph_match import (
    DEFAULT_NOISE_DOCUMENT_TYPES,
    KnowledgeGraph,
    NodeMatch,
    ServiceGraph,
    is_noise,
    load_knowledge_graph,
    load_service_graph,
    match_nodes,
    normalise_path,
    scope_service_graph,
)


def _rate(numerator: int, denominator: int) -> float:
    return round(numerator / denominator, 4) if denominator else 0.0


# --------------------------------------------------------------------------
# nodes
# --------------------------------------------------------------------------


def _build_missing_rows(
    unmatched_kg: list[dict[str, Any]],
    considered_ids: set[str],
    degrees: dict[str, dict[str, int]],
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for node in unmatched_kg:
        if node["content_id"] not in considered_ids:
            continue
        degree = degrees.get(node["content_id"], {"in": 0, "out": 0})
        rows.append(
            {
                "base_path": normalise_path(node.get("base_path")) or "",
                "title": node.get("title") or "",
                "document_type": node.get("document_type") or "",
                "in_degree": degree["in"],
                "out_degree": degree["out"],
                "description": (node.get("description") or "").replace("\n", " ")[:200],
            }
        )
    rows.sort(key=lambda r: (-r["in_degree"], -r["out_degree"], r["base_path"]))
    return rows


def _sg_only_reason(node: dict[str, Any], path: str | None) -> str:
    if node.get("off_platform"):
        return "off_platform"
    return "no_path" if not path else "not_reached_by_kg_crawl"


def _build_sg_only_rows(unmatched_sg: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for node in unmatched_sg:
        path = normalise_path(node.get("base_path")) or normalise_path(node.get("govuk_url"))
        rows.append(
            {
                "id": node["id"],
                "name": node.get("name") or "",
                "dept": node.get("dept") or "",
                "base_path": path or "",
                "off_platform": bool(node.get("off_platform")),
                "reason": _sg_only_reason(node, path),
            }
        )
    return rows


def compare_nodes(
    knowledge_graph: KnowledgeGraph,
    matches: list[NodeMatch],
    unmatched_kg: list[dict[str, Any]],
    unmatched_sg: list[dict[str, Any]],
    noise_types: set[str],
) -> tuple[dict[str, Any], list[dict[str, Any]], list[dict[str, Any]]]:
    degrees = knowledge_graph.degree()

    considered = [n for n in knowledge_graph.nodes if not is_noise(n, noise_types)]
    considered_ids = {n["content_id"] for n in considered}

    in_scope = [m for m in matches if m.sg_in_scope and m.kg_content_id in considered_ids]
    out_of_scope = [m for m in matches if not m.sg_in_scope and m.kg_content_id in considered_ids]

    missing_rows = _build_missing_rows(unmatched_kg, considered_ids, degrees)
    sg_only_rows = _build_sg_only_rows(unmatched_sg)

    summary = {
        "kg_nodes_total": len(knowledge_graph.nodes),
        "kg_nodes_excluded_as_noise": len(knowledge_graph.nodes) - len(considered),
        "kg_nodes_considered": len(considered),
        "matched_in_scope": len(in_scope),
        "matched_out_of_scope": len(out_of_scope),
        "missing_from_service_graph": len(missing_rows),
        "coverage_in_scope": _rate(len(in_scope), len(considered)),
        "coverage_any_scope": _rate(len(in_scope) + len(out_of_scope), len(considered)),
        "match_tiers": dict(Counter(m.tier for m in matches)),
        "missing_by_document_type": dict(
            Counter(r["document_type"] for r in missing_rows).most_common()
        ),
        "sg_scope_nodes": len(unmatched_sg) + len(in_scope),
        "sg_scope_matched": len(in_scope),
        "sg_scope_unmatched": len(unmatched_sg),
        "sg_scope_unmatched_reasons": dict(Counter(r["reason"] for r in sg_only_rows)),
        "sg_scope_precision": _rate(len(in_scope), len(unmatched_sg) + len(in_scope)),
    }
    return summary, missing_rows, sg_only_rows


# --------------------------------------------------------------------------
# edges
# --------------------------------------------------------------------------


def compare_edges(
    knowledge_graph: KnowledgeGraph,
    service_graph: ServiceGraph,
    matches: list[NodeMatch],
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    """
    Compare edges on the induced subgraph over matched nodes.

    Both directed and undirected agreement are reported. The service graph's
    RELATED edges are authored as an association rather than a direction, while
    KG links are genuinely directional, so undirected agreement is usually the
    number worth quoting and directed agreement tells you how often the two
    disagree purely on orientation.
    """
    kg_to_sg = {m.kg_content_id: m.sg_id for m in matches if m.sg_in_scope}

    kg_pairs_directed: set[tuple[str, str]] = set()
    for source, target in knowledge_graph.edges:
        sg_source, sg_target = kg_to_sg.get(source), kg_to_sg.get(target)
        if sg_source and sg_target and sg_source != sg_target:
            kg_pairs_directed.add((sg_source, sg_target))

    comparable_ids = set(kg_to_sg.values())
    sg_pairs_directed: set[tuple[str, str]] = set()
    sg_edge_type: dict[tuple[str, str], str] = {}
    for edge in service_graph.edges:
        source, target = edge["from"], edge["to"]
        if source in comparable_ids and target in comparable_ids and source != target:
            sg_pairs_directed.add((source, target))
            sg_edge_type[(source, target)] = edge.get("type", "")

    def undirected(pairs: set[tuple[str, str]]) -> set[tuple[str, str]]:
        return {tuple(sorted(pair)) for pair in pairs}

    kg_undirected = undirected(kg_pairs_directed)
    sg_undirected = undirected(sg_pairs_directed)

    both = kg_undirected & sg_undirected
    sg_only = sg_undirected - kg_undirected
    kg_only = kg_undirected - sg_undirected

    names = {m.sg_id: m.sg_name for m in matches}
    rows: list[dict[str, Any]] = []
    for pair in sorted(both | sg_only | kg_only):
        status = (
            "agreed" if pair in both else ("service_graph_only" if pair in sg_only else "kg_only")
        )
        edge_type = sg_edge_type.get(pair) or sg_edge_type.get((pair[1], pair[0])) or ""
        rows.append(
            {
                "source_id": pair[0],
                "target_id": pair[1],
                "source_name": names.get(pair[0], ""),
                "target_name": names.get(pair[1], ""),
                "status": status,
                "sg_edge_type": edge_type,
                "directed_agreement": pair in kg_pairs_directed and pair in sg_pairs_directed,
            }
        )

    union = len(kg_undirected | sg_undirected)
    summary = {
        "comparable_nodes": len(comparable_ids),
        "max_possible_pairs": len(comparable_ids) * (len(comparable_ids) - 1) // 2,
        "kg_edges_between_matched_nodes": len(kg_undirected),
        "sg_edges_between_matched_nodes": len(sg_undirected),
        "agreed": len(both),
        "service_graph_only": len(sg_only),
        "kg_only": len(kg_only),
        "edge_recall_vs_kg": _rate(len(both), len(kg_undirected)),
        "edge_precision_vs_kg": _rate(len(both), len(sg_undirected)),
        "jaccard": _rate(len(both), union),
        "directed_agreement": len(kg_pairs_directed & sg_pairs_directed),
        "kg_edge_types_available": knowledge_graph.edge_types_available,
    }
    return summary, rows


# --------------------------------------------------------------------------
# output
# --------------------------------------------------------------------------


def write_csv(path: Path, rows: list[dict[str, Any]], columns: list[str]) -> None:
    with path.open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=columns)
        writer.writeheader()
        writer.writerows(rows)


def print_report(report: dict[str, Any], missing_rows: list[dict[str, Any]]) -> None:
    nodes = report["nodes"]
    edges = report["edges"]

    print("\n" + "=" * 72)
    print(f"NODES  (life event: {report['life_event']}, sg scope: {report['sg_scope_mode']})")
    print("=" * 72)
    print(f"  KG nodes                        {nodes['kg_nodes_total']}")
    print(f"    excluded as noise             {nodes['kg_nodes_excluded_as_noise']}")
    print(f"    considered                    {nodes['kg_nodes_considered']}")
    print(f"  matched, in life-event scope    {nodes['matched_in_scope']}")
    print(f"  matched, out of scope           {nodes['matched_out_of_scope']}  (wiring gap)")
    print(f"  missing entirely                {nodes['missing_from_service_graph']}")
    print(f"  coverage (in scope)             {nodes['coverage_in_scope']:.1%}")
    print(f"  coverage (any scope)            {nodes['coverage_any_scope']:.1%}")
    print(f"  match tiers                     {nodes['match_tiers']}")
    print()
    print(f"  service-graph scope size        {nodes['sg_scope_nodes']}")
    print(f"    matched to KG                 {nodes['sg_scope_matched']}")
    print(
        f"    unmatched                     {nodes['sg_scope_unmatched']} "
        f"{nodes['sg_scope_unmatched_reasons']}"
    )

    print("\n  Missing, by document type:")
    for document_type, count in nodes["missing_by_document_type"].items():
        print(f"    {document_type:24} {count}")

    print("\n  Top missing nodes by in-degree:")
    for row in missing_rows[:15]:
        print(f"    {row['in_degree']:>3} in  {row['base_path']:<52} {row['title'][:40]}")

    print("\n" + "=" * 72)
    print("EDGES  (induced over matched, in-scope nodes only)")
    print("=" * 72)
    print(
        f"  comparable nodes                {edges['comparable_nodes']} "
        f"({edges['max_possible_pairs']} possible pairs)"
    )
    print(f"  KG edges between them           {edges['kg_edges_between_matched_nodes']}")
    print(f"  service-graph edges between them{edges['sg_edges_between_matched_nodes']:>4}")
    print(f"  agreed (undirected)             {edges['agreed']}")
    print(f"  service-graph only              {edges['service_graph_only']}")
    print(f"  KG only                         {edges['kg_only']}")
    print(
        f"  recall / precision / jaccard    {edges['edge_recall_vs_kg']:.2f} / "
        f"{edges['edge_precision_vs_kg']:.2f} / {edges['jaccard']:.2f}"
    )
    print(f"  of which directed agreement     {edges['directed_agreement']}")
    if not edges["kg_edge_types_available"]:
        print(
            "\n  NOTE: the KG edges carry no 'type' column, so link semantics "
            "(related_items vs ordered_related_items vs part_of) cannot be\n"
            "        compared. graph_crawler._prune_with_reconnect rebuilds the "
            "frame from (source, target) only; carry 'type' through if you\n"
            "        want typed edge comparison."
        )
    print()


def main() -> None:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--kg", required=True, help="knowledge-graph subgraph JSON")
    parser.add_argument("--sg", required=True, help="service-graph export JSON")
    parser.add_argument("--life-event", default=None, help="service-graph life event id")
    parser.add_argument(
        "--sg-scope",
        choices=["life_event", "dept", "all"],
        default="life_event",
        help="which service-graph nodes count as in scope (default: life_event)",
    )
    parser.add_argument("--dept-keys", nargs="*", default=["dvla", "dvsa"])
    parser.add_argument(
        "--undirected-scope",
        action="store_true",
        help="traverse service-graph edges in both directions when scoping",
    )
    parser.add_argument(
        "--keep-noise",
        action="store_true",
        help="include /done/ pages, news stories etc. in the denominator",
    )
    parser.add_argument("--no-parent-match", action="store_true", help="require exact path matches")
    parser.add_argument("--out", default="reports", help="output directory")
    args = parser.parse_args()

    knowledge_graph = load_knowledge_graph(args.kg)
    service_graph = load_service_graph(args.sg)
    life_event = args.life_event or knowledge_graph.life_event

    scope_ids = scope_service_graph(
        service_graph,
        mode=args.sg_scope,
        life_event_id=life_event,
        dept_keys=args.dept_keys,
        undirected=args.undirected_scope,
    )

    matches, unmatched_kg, unmatched_sg = match_nodes(
        knowledge_graph,
        service_graph,
        scope_ids,
        allow_parent_match=not args.no_parent_match,
    )

    noise_types: set[str] = set() if args.keep_noise else set(DEFAULT_NOISE_DOCUMENT_TYPES)

    node_summary, missing_rows, sg_only_rows = compare_nodes(
        knowledge_graph, matches, unmatched_kg, unmatched_sg, noise_types
    )
    edge_summary, edge_rows = compare_edges(knowledge_graph, service_graph, matches)

    report = {
        "life_event": life_event,
        "sg_scope_mode": args.sg_scope,
        "sg_scope_size": len(scope_ids),
        "noise_document_types_excluded": sorted(noise_types),
        "nodes": node_summary,
        "edges": edge_summary,
    }

    out_dir = Path(args.out).resolve()
    allowed_root = Path.cwd().resolve()
    if not out_dir.is_relative_to(allowed_root):
        raise SystemExit(
            f"Output directory {out_dir} is outside the working directory {allowed_root}"
        )
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / f"{life_event}_comparison.json").write_text(json.dumps(report, indent=2))
    write_csv(
        out_dir / f"{life_event}_missing_nodes.csv",
        missing_rows,
        ["base_path", "title", "document_type", "in_degree", "out_degree", "description"],
    )
    write_csv(
        out_dir / f"{life_event}_service_graph_only_nodes.csv",
        sg_only_rows,
        ["id", "name", "dept", "base_path", "off_platform", "reason"],
    )
    write_csv(
        out_dir / f"{life_event}_edge_diff.csv",
        edge_rows,
        [
            "source_id",
            "target_id",
            "source_name",
            "target_name",
            "status",
            "sg_edge_type",
            "directed_agreement",
        ],
    )
    write_csv(
        out_dir / f"{life_event}_matched_nodes.csv",
        [
            {
                "kg_path": m.kg_path,
                "kg_title": m.kg_title,
                "kg_document_type": m.kg_document_type,
                "sg_id": m.sg_id,
                "sg_name": m.sg_name,
                "tier": m.tier,
                "sg_in_scope": m.sg_in_scope,
            }
            for m in sorted(matches, key=lambda m: (not m.sg_in_scope, m.kg_path))
        ],
        ["kg_path", "kg_title", "kg_document_type", "sg_id", "sg_name", "tier", "sg_in_scope"],
    )

    print_report(report, missing_rows)
    print(f"Wrote report and 4 CSVs to {out_dir}/\n")


if __name__ == "__main__":
    main()
