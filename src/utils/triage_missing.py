"""
This script groups the KG nodes absent from the service-graph by
*why* they are probably absent, rather than by document_type.

Three independent axes:

  anchor    Which matched service-graph node is this page nearest to in the KG
            subgraph? Computed by BFS over the undirected KG edges. Turns a
            flat list of absent pages into a handful of service clusters, and
            distinguishes "satellite of a service you already model" from
            "orphan in territory you don't cover at all".

  audience  Citizen, or trade/professional? The service-graph models citizens
            navigating life events, so ADI, HGV, taxi and ADR pages are a
            deliberate scope boundary, not an omission.

  role      Is this a distinct service, a lifecycle satellite of one
            (check/change/cancel/find/track), reference material with nothing
            to apply for, cost information, or a contact route?

Cross-tabulating audience x role turns "73 missing" into a few numbers you can
defend in a writeup, and the residual cell — citizen x service, no anchor
excuse — is the actual backlog.

Usage:
    python triage_missing.py --kg data/driving_subgraph.json \
        --sg mcp-servers/service-graph/src/service-graph-export.json --life-event driving \
        --sg-scope dept --dept-keys dvla dvsa jaqu --out data/
"""

from __future__ import annotations

import argparse
import csv
import json
import re
from collections import Counter, defaultdict, deque
from pathlib import Path
from typing import Any

from graph_match import (
    DEFAULT_NOISE_DOCUMENT_TYPES,
    load_knowledge_graph,
    load_service_graph,
    match_nodes,
    normalise_path,
    scope_service_graph,
)

# --------------------------------------------------------------------------
# rule tables — edit these; they are the whole point of the script
# --------------------------------------------------------------------------

TRADE_PATTERNS = [
    r"instructor",
    r"\badi\b",
    r"lorry|bus|hgv|\bpcv\b",
    r"dangerous-goods|\badr\b",
    r"driver-cpc|\bcpc\b",
    r"taxi|private-hire",
    r"tractor|specialist-vehicle",
    r"observing-driving-tests",
    r"motor-trader",
    r"emergency-driving-test",  # critical-worker route, not the public one
]

VEHICLE_PATTERNS = {
    "motorcycle": r"motorcycle|moped|motorbike|\bcbt\b|rider|helmet|motor-tricycle",
    "towing": r"tow|trailer|caravan|vehicle-weights",
    "hgv": r"lorry|bus|hgv|dangerous-goods|\badr\b",
}

# Lifecycle verbs: GOV.UK splits one service across several transaction pages.
# The service-graph models the service as a single node, so these are a
# granularity difference rather than missing coverage.
SATELLITE_PREFIXES = ("check-", "change-", "cancel-", "find-", "track-", "done/")
SATELLITE_PATTERNS = [
    r"^/take-practice-",
    r"^/check-change-cancel-",
    r"-pass-number$",
    r"^/replace-cbt-certificate$",
]

REFERENCE_DOCUMENT_TYPES = {
    "guidance",
    "statutory_guidance",
    "detailed_guide",
    "manual",
    "form",
    "news_story",
    "step_by_step_nav",
}
REFERENCE_PATTERNS = [
    r"^/speed-limits$",
    r"^/driving-licence-(categories|codes)$",
    r"^/legal-obligations",
    r"^/vehicles-can-drive$",
    r"^/towing-rules$",
    r"^/vehicle-weights",
    r"^/driving-eyesight-rules$",
    r"^/vehicle-exempt-from-vehicle-tax$",
]

COST_PATTERNS = [r"-cost$", r"-fees$", r"fees$"]
CONTACT_PATTERNS = [r"^/contact-", r"^/dvlaforms$", r"^/report-", r"^/complain-"]


def _matches(path: str, title: str, patterns: list[str]) -> bool:
    haystack = f"{path} {title}".lower()
    return any(re.search(pattern, haystack) for pattern in patterns)


def classify_audience(path: str, title: str) -> str:
    return "trade" if _matches(path, title, TRADE_PATTERNS) else "citizen"


def classify_vehicle(path: str, title: str) -> str:
    for label, pattern in VEHICLE_PATTERNS.items():
        if _matches(path, title, [pattern]):
            return label
    return "car_general"


def classify_role(path: str, title: str, document_type: str) -> str:
    stem = path.lstrip("/")
    if stem.startswith(SATELLITE_PREFIXES) or _matches(path, title, SATELLITE_PATTERNS):
        return "lifecycle_satellite"
    if _matches(path, title, CONTACT_PATTERNS):
        return "contact_or_complaint"
    if _matches(path, title, COST_PATTERNS):
        return "cost_information"
    if document_type in REFERENCE_DOCUMENT_TYPES or _matches(path, title, REFERENCE_PATTERNS):
        return "reference_content"
    return "candidate_service"


# --------------------------------------------------------------------------
# anchoring
# --------------------------------------------------------------------------


def nearest_anchors(
    knowledge_graph, anchor_content_ids: set[str], max_hops: int = 3
) -> dict[str, tuple[str | None, int]]:
    """
    Multi-source BFS outward from every matched node over undirected KG edges.
    Returns content_id -> (nearest anchor content_id, hop distance).
    """
    adjacency: dict[str, set[str]] = defaultdict(set)
    for source, target in knowledge_graph.edges:
        adjacency[source].add(target)
        adjacency[target].add(source)

    result: dict[str, tuple[str | None, int]] = {
        node_id: (node_id, 0) for node_id in anchor_content_ids
    }
    queue = deque((node_id, node_id, 0) for node_id in anchor_content_ids)
    while queue:
        current, anchor, distance = queue.popleft()
        if distance >= max_hops:
            continue
        for neighbour in adjacency.get(current, ()):
            if neighbour in result:
                continue
            result[neighbour] = (anchor, distance + 1)
            queue.append((neighbour, anchor, distance + 1))

    for node in knowledge_graph.nodes:
        result.setdefault(node["content_id"], (None, -1))
    return result


# --------------------------------------------------------------------------


def main() -> None:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--kg", required=True)
    parser.add_argument("--sg", required=True)
    parser.add_argument("--life-event", default=None)
    parser.add_argument("--sg-scope", choices=["life_event", "dept", "all"], default="dept")
    parser.add_argument("--dept-keys", nargs="*", default=["dvla", "dvsa", "jaqu"])
    parser.add_argument("--keep-noise", action="store_true")
    parser.add_argument("--max-hops", type=int, default=3)
    parser.add_argument("--out", default="reports")
    args = parser.parse_args()

    knowledge_graph = load_knowledge_graph(args.kg)
    service_graph = load_service_graph(args.sg)
    life_event = args.life_event or knowledge_graph.life_event

    scope_ids = scope_service_graph(
        service_graph, mode=args.sg_scope, life_event_id=life_event, dept_keys=args.dept_keys
    )
    matches, unmatched_kg, _ = match_nodes(knowledge_graph, service_graph, scope_ids)

    anchors = nearest_anchors(
        knowledge_graph, {m.kg_content_id for m in matches}, max_hops=args.max_hops
    )
    anchor_names = {m.kg_content_id: m.sg_id for m in matches}
    noise = set() if args.keep_noise else set(DEFAULT_NOISE_DOCUMENT_TYPES)

    rows: list[dict[str, Any]] = []
    for node in unmatched_kg:
        document_type = node.get("document_type") or ""
        if document_type in noise:
            continue
        path = normalise_path(node.get("base_path")) or ""
        title = node.get("title") or ""
        anchor_id, distance = anchors.get(node["content_id"], (None, -1))
        rows.append(
            {
                "base_path": path,
                "title": title,
                "document_type": document_type,
                "audience": classify_audience(path, title),
                "vehicle": classify_vehicle(path, title),
                "role": classify_role(path, title, document_type),
                "anchor_sg_id": anchor_names.get(anchor_id or "", "") or "NONE",
                "anchor_hops": distance,
            }
        )

    def crosstab(row_key: str, column_key: str) -> None:
        table: dict[str, Counter] = defaultdict(Counter)
        for row in rows:
            table[row[row_key]][row[column_key]] += 1
        columns = sorted({row[column_key] for row in rows})
        width = max(len(c) for c in columns + [row_key]) + 2
        print(f"\n{row_key} x {column_key}")
        print(" " * 22 + "".join(f"{c:>{width}}" for c in columns) + f"{'total':>9}")
        for key in sorted(table):
            counts = table[key]
            line = "".join(f"{counts[c] or '':>{width}}" for c in columns)
            print(f"  {key:<20}{line}{sum(counts.values()):>9}")

    print(f"\n{len(rows)} absent nodes (life event: {life_event}, scope: {args.sg_scope})")
    crosstab("audience", "role")
    crosstab("vehicle", "role")

    print("\nClusters — absent pages by nearest modelled service:")
    clusters: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        clusters[row["anchor_sg_id"]].append(row)
    for anchor, members in sorted(clusters.items(), key=lambda kv: -len(kv[1])):
        print(f"\n  {anchor}  ({len(members)})")
        for row in sorted(members, key=lambda r: (r["anchor_hops"], r["base_path"]))[:12]:
            print(
                f"    {row['anchor_hops']}hop  {row['role']:<21} {row['audience']:<8} {row['base_path']}"
            )

    backlog = [
        r
        for r in rows
        if r["audience"] == "citizen"
        and r["vehicle"] == "car_general"
        and r["role"] == "candidate_service"
    ]
    print(f"\nResidual backlog (citizen, car, candidate_service): {len(backlog)}")
    for row in sorted(backlog, key=lambda r: r["base_path"]):
        print(f"    {row['base_path']:<52} {row['title'][:44]}")

    out_dir = Path(args.out).resolve()
    allowed_root = Path.cwd().resolve()
    if not out_dir.is_relative_to(allowed_root):
        raise SystemExit(
            f"Output directory {out_dir} is outside the working directory {allowed_root}"
        )
    out_dir.mkdir(parents=True, exist_ok=True)
    with (out_dir / f"{life_event}_missing_triage.csv").open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)
    (out_dir / f"{life_event}_missing_triage_summary.json").write_text(
        json.dumps(
            {
                "total": len(rows),
                "by_audience": dict(Counter(r["audience"] for r in rows)),
                "by_role": dict(Counter(r["role"] for r in rows)),
                "by_vehicle": dict(Counter(r["vehicle"] for r in rows)),
                "by_anchor": {
                    k: len(v) for k, v in sorted(clusters.items(), key=lambda kv: -len(kv[1]))
                },
                "residual_backlog": [r["base_path"] for r in backlog],
            },
            indent=2,
        )
    )
    print(f"\nWrote triage CSV + summary to {out_dir}/\n")


if __name__ == "__main__":
    main()
