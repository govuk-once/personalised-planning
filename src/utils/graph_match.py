"""
This module contains shared utilities for loading, normalisation and node-matching logic used to
compare the GOV.UK knowledge-graph (KG) subgraph against the hand-curated
service-graph (SG).

Inputs
------
KG subgraph  : output of src/utils/build_subgraph.py
               {"life_event": str,
                "nodes": [{content_id, base_path, title, description,
                           document_type, details}],
                "edges": [{source_content_id, target_content_id}]}

Service graph: output of mcp-servers/service-graph/src/dump-graph.ts
               {"nodes": [{id, name, dept, base_path, govuk_url,
                           off_platform, serviceType, eligibility, ...}],
                "edges": [{from, to, type}],
                "life_events": [{id, name, entryNodes}]}
"""

from __future__ import annotations

import json
from collections import defaultdict, deque
from collections.abc import Iterable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal

# GOV.UK document types that are structurally part of the site but are not
# immediately useful for a citizen to access services.
DEFAULT_NOISE_DOCUMENT_TYPES = frozenset(
    {
        "completed_transaction",  # /done/... feedback pages
        "news_story",
        "redirect",
        "gone",
    }
)

GOVUK_HOSTS = frozenset({"www.gov.uk", "gov.uk"})

MatchTier = Literal["exact", "parent", "child", "none"]
ScopeMode = Literal["life_event", "dept", "all"]


# --------------------------------------------------------------------------
# path normalisation
# --------------------------------------------------------------------------


def normalise_path(value: str | None) -> str | None:
    """
    Reduce a base_path or a full GOV.UK URL to a comparable path.

        https://www.gov.uk/vehicle-tax/  ->  /vehicle-tax
        /Vehicle-Tax?foo=1#bar           ->  /vehicle-tax

    Returns None for anything that is not a usable GOV.UK path: empty values,
    and any host outside GOVUK_HOSTS.

    *.service.gov.uk transaction start pages are
    excluded because they have no publishing-api content item,
    so there is nothing in the knowledge graph for them to match.
    """
    if not value or not isinstance(value, str):
        return None

    path = value.strip()
    if "://" in path:
        host, _, remainder = path.split("://", 1)[1].partition("/")
        if host.split(":")[0].lower() not in GOVUK_HOSTS:
            return None
        path = "/" + remainder

    path = path.split("?", 1)[0].split("#", 1)[0]
    path = path.rstrip("/").lower()
    if not path.startswith("/"):
        return None
    return path or None


def parent_path(path: str) -> str | None:
    """'/theory-test/hazard-perception' -> '/theory-test'. None if already top level."""
    trimmed = path.rstrip("/")
    if trimmed.count("/") <= 1:
        return None
    return trimmed.rsplit("/", 1)[0]


# --------------------------------------------------------------------------
# graph containers
# --------------------------------------------------------------------------


@dataclass
class KnowledgeGraph:
    """The BigQuery-derived subgraph for one life event."""

    life_event: str
    nodes: list[dict[str, Any]]
    edges: list[tuple[str, str]]
    edge_types_available: bool
    by_content_id: dict[str, dict[str, Any]] = field(default_factory=dict)
    by_path: dict[str, dict[str, Any]] = field(default_factory=dict)

    def degree(self) -> dict[str, dict[str, int]]:
        """In/out degree per content_id within the subgraph."""
        counts: dict[str, dict[str, int]] = {
            n["content_id"]: {"in": 0, "out": 0} for n in self.nodes
        }
        for source, target in self.edges:
            if source in counts:
                counts[source]["out"] += 1
            if target in counts:
                counts[target]["in"] += 1
        return counts


@dataclass
class ServiceGraph:
    """The hand-curated service graph."""

    nodes: list[dict[str, Any]]
    edges: list[dict[str, Any]]
    life_events: list[dict[str, Any]]
    by_id: dict[str, dict[str, Any]] = field(default_factory=dict)
    by_path: dict[str, dict[str, Any]] = field(default_factory=dict)

    def life_event(self, life_event_id: str) -> dict[str, Any] | None:
        for event in self.life_events:
            if event.get("id") == life_event_id:
                return event
        return None


def load_knowledge_graph(path: str | Path) -> KnowledgeGraph:
    raw = json.loads(Path(path).read_text())

    nodes = raw["nodes"]
    raw_edges = raw["edges"]
    # build_life_event_subgraph() prunes with reconnect_through_pruned=True,
    # and _prune_with_reconnect rebuilds the frame from (source, target) pairs
    # only — so link 'type' is dropped upstream. Detect that rather than assume.
    edge_types_available = bool(raw_edges) and "type" in raw_edges[0]

    edges = [(e["source_content_id"], e["target_content_id"]) for e in raw_edges]

    graph = KnowledgeGraph(
        life_event=raw.get("life_event", "unknown"),
        nodes=nodes,
        edges=edges,
        edge_types_available=edge_types_available,
    )
    graph.by_content_id = {n["content_id"]: n for n in nodes}
    for node in nodes:
        normalised = normalise_path(node.get("base_path"))
        if normalised and normalised not in graph.by_path:
            graph.by_path[normalised] = node
    return graph


def load_service_graph(path: str | Path) -> ServiceGraph:
    raw = json.loads(Path(path).read_text())

    graph = ServiceGraph(
        nodes=raw["nodes"],
        edges=raw["edges"],
        life_events=raw.get("life_events", []),
    )
    graph.by_id = {n["id"]: n for n in raw["nodes"]}
    for node in raw["nodes"]:
        normalised = normalise_path(node.get("base_path")) or normalise_path(node.get("govuk_url"))
        if normalised and normalised not in graph.by_path:
            graph.by_path[normalised] = node
    return graph


# --------------------------------------------------------------------------
# scoping the service graph
# --------------------------------------------------------------------------


def scope_service_graph(
    service_graph: ServiceGraph,
    mode: ScopeMode = "life_event",
    life_event_id: str | None = None,
    dept_keys: Iterable[str] | None = None,
    undirected: bool = False,
) -> set[str]:
    """
    Decide which service-graph nodes count as "in scope" for this life event.

    life_event : BFS from the life event's entryNodes over the edge list. This
                 is what the planner agent can actually reach at runtime, so it
                 is the honest denominator for a coverage claim.
    dept       : every node owned by the given departments, regardless of
                 whether the life event reaches it. Useful for separating
                 "the node does not exist" from "the node exists but is not
                 wired into this life event".
    all        : every node in the service graph.
    """
    if mode == "all":
        return set(service_graph.by_id)

    if mode == "dept":
        wanted = {key.lower() for key in (dept_keys or [])}
        return {
            n["id"]
            for n in service_graph.nodes
            if str(n.get("deptKey", "")).lower() in wanted
            or str(n.get("dept", "")).lower() in wanted
        }

    if not life_event_id:
        raise ValueError("life_event scope requires life_event_id")
    event = service_graph.life_event(life_event_id)
    if event is None:
        available = ", ".join(sorted(e.get("id", "?") for e in service_graph.life_events))
        raise ValueError(f"life event {life_event_id!r} not found. Available: {available}")

    adjacency: dict[str, list[str]] = defaultdict(list)
    for edge in service_graph.edges:
        adjacency[edge["from"]].append(edge["to"])
        if undirected:
            adjacency[edge["to"]].append(edge["from"])

    reachable: set[str] = set()
    queue = deque(event.get("entryNodes", []))
    while queue:
        node_id = queue.popleft()
        if node_id in reachable:
            continue
        reachable.add(node_id)
        queue.extend(adjacency.get(node_id, []))
    return reachable


# --------------------------------------------------------------------------
# node matching
# --------------------------------------------------------------------------


@dataclass
class NodeMatch:
    kg_content_id: str
    kg_path: str
    kg_title: str
    kg_document_type: str
    sg_id: str
    sg_name: str
    sg_path: str | None
    tier: MatchTier
    sg_in_scope: bool


def _match_exact(
    kg_by_path: dict[str, dict[str, Any]],
    sg_by_path: dict[str, dict[str, Any]],
) -> list[tuple[dict[str, Any], dict[str, Any]]]:
    pairs: list[tuple[dict[str, Any], dict[str, Any]]] = []
    for path, kg_node in kg_by_path.items():
        sg_node = sg_by_path.get(path)
        if sg_node is not None:
            pairs.append((kg_node, sg_node))
    return pairs


def _match_by_parent(
    source_by_path: dict[str, dict[str, Any]],
    target_by_path: dict[str, dict[str, Any]],
    skip_source_ids: set[str],
    skip_target_ids: set[str],
    source_id_key: str,
    target_id_key: str,
) -> list[tuple[dict[str, Any], dict[str, Any]]]:
    pairs: list[tuple[dict[str, Any], dict[str, Any]]] = []
    for path, source_node in source_by_path.items():
        if source_node[source_id_key] in skip_source_ids:
            continue
        candidate = parent_path(path)
        if candidate is None:
            continue
        target_node = target_by_path.get(candidate)
        if target_node is None:
            continue
        if target_node[target_id_key] in skip_target_ids:
            continue
        pairs.append((target_node, source_node))
        skip_source_ids.add(source_node[source_id_key])
        skip_target_ids.add(target_node[target_id_key])
    return pairs


def _build_match(
    kg_node: dict[str, Any],
    sg_node: dict[str, Any],
    tier: MatchTier,
    scope_ids: set[str],
) -> NodeMatch:
    return NodeMatch(
        kg_content_id=kg_node["content_id"],
        kg_path=normalise_path(kg_node.get("base_path")) or "",
        kg_title=kg_node.get("title") or "",
        kg_document_type=kg_node.get("document_type") or "",
        sg_id=sg_node["id"],
        sg_name=sg_node.get("name") or "",
        sg_path=normalise_path(sg_node.get("base_path"))
        or normalise_path(sg_node.get("govuk_url")),
        tier=tier,
        sg_in_scope=sg_node["id"] in scope_ids,
    )


def match_nodes(
    knowledge_graph: KnowledgeGraph,
    service_graph: ServiceGraph,
    scope_ids: set[str],
    allow_parent_match: bool = True,
) -> tuple[list[NodeMatch], list[dict[str, Any]], list[dict[str, Any]]]:
    """
    Match KG nodes to SG nodes on normalised path.

    Tiers, applied in order:
      exact  — identical normalised path.
      parent — the SG node points at a sub-page of a KG node
               (/financial-help-disabled/vehicles-and-transport -> /financial-help-disabled).
               GOV.UK guides are one content item with many part paths, so this
               is a real identity, not a fuzzy guess.
      child  — the reverse: a KG part-path resolving up to an SG node.

    Returns (matches, unmatched_kg_nodes, unmatched_sg_nodes_in_scope).
    """
    matches: list[NodeMatch] = []
    matched_kg_ids: set[str] = set()
    matched_sg_ids: set[str] = set()

    for kg_node, sg_node in _match_exact(knowledge_graph.by_path, service_graph.by_path):
        matches.append(_build_match(kg_node, sg_node, "exact", scope_ids))
        matched_kg_ids.add(kg_node["content_id"])
        matched_sg_ids.add(sg_node["id"])

    if allow_parent_match:
        parent_pairs = _match_by_parent(
            service_graph.by_path,
            knowledge_graph.by_path,
            matched_sg_ids,
            matched_kg_ids,
            "id",
            "content_id",
        )
        for kg_node, sg_node in parent_pairs:
            matches.append(_build_match(kg_node, sg_node, "parent", scope_ids))

        child_pairs = _match_by_parent(
            knowledge_graph.by_path,
            service_graph.by_path,
            matched_kg_ids,
            matched_sg_ids,
            "content_id",
            "id",
        )
        for sg_node, kg_node in child_pairs:
            matches.append(_build_match(kg_node, sg_node, "child", scope_ids))

    unmatched_kg = [n for n in knowledge_graph.nodes if n["content_id"] not in matched_kg_ids]
    unmatched_sg = [service_graph.by_id[node_id] for node_id in sorted(scope_ids - matched_sg_ids)]
    return matches, unmatched_kg, unmatched_sg


def is_noise(node: dict[str, Any], noise_types: Iterable[str]) -> bool:
    return (node.get("document_type") or "") in set(noise_types)


# --------------------------------------------------------------------------
# GOV.UK content extraction (used by the LLM judge)
# --------------------------------------------------------------------------

_CONTENT_KEYS_TO_SKIP = {"external_related_links", "change_history", "attachments"}


def _pick_typed_content(items: list[dict[str, Any]], preferred: str, fallback: str) -> list[str]:
    typed = [i for i in items if isinstance(i, dict) and "content_type" in i and "content" in i]
    if not typed:
        return []
    chosen = [i for i in typed if i["content_type"] == preferred]
    if not chosen:
        chosen = [i for i in typed if i["content_type"] == fallback]
    return [str(i["content"]) for i in chosen]


def _walk_content_tree(node: Any, chunks: list[str], preferred: str, fallback: str) -> None:
    if isinstance(node, list):
        picked = _pick_typed_content(node, preferred, fallback)
        if picked:
            chunks.extend(picked)
            return
        for item in node:
            _walk_content_tree(item, chunks, preferred, fallback)
        return

    if not isinstance(node, dict):
        return

    title = node.get("title") or node.get("label")
    if title and isinstance(title, str):
        chunks.append(f"\n## {title}\n")
    for key, value in node.items():
        if key in _CONTENT_KEYS_TO_SKIP:
            continue
        if key == "content" and isinstance(value, str):
            chunks.append(value)
        elif isinstance(value, (list, dict)):
            _walk_content_tree(value, chunks, preferred, fallback)


def extract_content_text(
    details: str | dict[str, Any] | None,
    prefer: Literal["govspeak", "html"] = "govspeak",
    max_chars: int = 20000,
) -> str:
    """
    Flatten the publishing-api `details` blob into readable text.

    `details` is a JSON string holding a document-type-specific structure:
    a plain `body`, a list of govspeak/html content blocks, `parts` for guides,
    `nodes` for smart answers, `introductory_paragraph` for transactions, and
    so on. Rather than special-casing every document type, walk the tree and
    collect every content block, preferring govspeak (roughly half the tokens
    of the equivalent HTML, and it keeps GOV.UK internal links as markdown).
    """
    if not details:
        return ""
    if isinstance(details, str):
        try:
            details = json.loads(details)
        except json.JSONDecodeError:
            return details[:max_chars]

    chunks: list[str] = []
    preferred_mime = f"text/{prefer}"
    fallback_mime = "text/html" if prefer == "govspeak" else "text/govspeak"
    _walk_content_tree(details, chunks, preferred_mime, fallback_mime)

    text = "\n\n".join(chunk.strip() for chunk in chunks if str(chunk).strip())
    text = text.replace("\r\n", "\n")
    if len(text) > max_chars:
        text = text[:max_chars] + "\n\n[... truncated ...]"
    return text
