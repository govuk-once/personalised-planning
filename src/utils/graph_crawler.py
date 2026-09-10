"""
Utilities for building a life-event subgraph from already-loaded
edges_df / nodes_df, which are separately pulled from govuk-knowledge graph using query_knowledge_graph.py.

Discovery mechanism: look up everything GOV.UK tags under a given mainstream_browse_page via the
'mainstream_browse_pages' link type.

"""

from collections import defaultdict, deque
from collections.abc import Iterable

import pandas as pd

START_CONTENT_ID = "e01e924b-9c7c-4c71-8241-66a575c2f61f"  # /learn-to-drive-a-car


def crawl_graph_local(
    edges_df: pd.DataFrame,
    start_content_id: str,
    max_depth: int | None = None,
) -> pd.DataFrame:
    """
    BFS from start_content_id over an already-loaded edges_df, entirely in
    memory — no further BigQuery calls. Same cycle-safety as the per-node
    version (a node is only expanded once via `visited`), but effectively
    free and near-instant since it's just dict lookups.

    Returns the subset of edges_df reachable from start_content_id.
    """
    # Build an adjacency lookup once: source_content_id -> list of row indices
    adjacency: dict = defaultdict(list)
    for idx, source_id in enumerate(edges_df["source_content_id"].values):
        adjacency[source_id].append(idx)

    visited: set[str] = set()
    reachable_row_indices: list[int] = []
    queue: deque = deque([(start_content_id, 0)])

    while queue:
        content_id, depth = queue.popleft()
        if content_id in visited:
            continue
        visited.add(content_id)

        if max_depth is not None and depth >= max_depth:
            continue

        for idx in adjacency.get(content_id, []):
            reachable_row_indices.append(idx)
            target = edges_df["target_content_id"].iat[idx]
            if target and target not in visited:
                queue.append((target, depth + 1))

    return edges_df.iloc[reachable_row_indices].reset_index(drop=True)


def dedupe_edges(edges: Iterable[dict]) -> pd.DataFrame:
    """Dedupe on (source_content_id, target_content_id) pair."""
    df = pd.DataFrame(edges)
    if df.empty:
        return df
    return df.drop_duplicates(subset=["source_content_id", "target_content_id"]).reset_index(
        drop=True
    )


def all_node_ids_from_edges(edges_df: pd.DataFrame) -> set[str]:
    """Convenience: union of every source and target content_id seen in the edge list."""
    return set(edges_df["source_content_id"]).union(set(edges_df["target_content_id"]))


def _resolve_keep_mask(
    nodes_df: pd.DataFrame,
    property_column: str,
    keep_values: Iterable[str] | None,
    exclude_values: Iterable[str] | None,
) -> pd.Series:
    """Validate keep/exclude args and return the boolean mask of nodes to keep."""
    if (keep_values is None) == (exclude_values is None):
        raise ValueError("Provide exactly one of keep_values or exclude_values")

    if keep_values is not None:
        return nodes_df[property_column].isin(list(keep_values))
    return ~nodes_df[property_column].isin(list(exclude_values))


def _prune_without_reconnect(edges_df: pd.DataFrame, kept_ids: set[str]) -> pd.DataFrame:
    """Simple case: drop any edge touching a pruned node."""
    return edges_df[
        edges_df["source_content_id"].isin(kept_ids) & edges_df["target_content_id"].isin(kept_ids)
    ].reset_index(drop=True)


def _nearest_kept_descendants(
    node_id: str,
    forward: dict,
    kept_ids: set[str],
    dropped_ids: set[str],
    seen: set[str],
) -> set[str]:
    """Walk forward through dropped nodes until kept nodes are reached."""
    results = set()
    for target in forward.get(node_id, []):
        if target in seen:
            continue
        seen.add(target)
        if target in kept_ids:
            results.add(target)
        elif target in dropped_ids:
            results |= _nearest_kept_descendants(target, forward, kept_ids, dropped_ids, seen)
    return results


def _prune_with_reconnect(
    edges_df: pd.DataFrame, kept_ids: set[str], dropped_ids: set[str]
) -> pd.DataFrame:
    """Reconnect mode: skip over dropped nodes to wire kept nodes directly together."""
    forward = defaultdict(list)
    for row in edges_df.itertuples(index=False):
        forward[row.source_content_id].append(row.target_content_id)

    new_edges = set()
    for source_id in kept_ids:
        for target in forward.get(source_id, []):
            if target in kept_ids:
                new_edges.add((source_id, target))
            elif target in dropped_ids:
                descendants = _nearest_kept_descendants(
                    target, forward, kept_ids, dropped_ids, set()
                )
                for reconnected_target in descendants:
                    new_edges.add((source_id, reconnected_target))

    return pd.DataFrame(new_edges, columns=["source_content_id", "target_content_id"])


def prune_graph_by_property(
    edges_df: pd.DataFrame,
    nodes_df: pd.DataFrame,
    property_column: str,
    keep_values: Iterable[str] | None = None,
    exclude_values: Iterable[str] | None = None,
    reconnect_through_pruned: bool = False,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """
    Prune the graph based on a node property (e.g. document_type).

    Exactly one of keep_values / exclude_values should be provided:
      - keep_values: only nodes whose property_column is in this set are kept
      - exclude_values: nodes whose property_column is in this set are dropped

    reconnect_through_pruned:
      - False (default): edges touching a pruned node are simply dropped, so
        pruning a node also removes the paths that ran through it.
      - True: pruned nodes are skipped over rather than cutting the graph —
        an edge A -> B -> C, where B is pruned, becomes A -> C. Useful when
        you want to drop e.g. "redirect" or "gone" pages without losing
        connectivity between the real content either side of them.

    Returns (pruned_edges_df, pruned_nodes_df).
    """
    keep_mask = _resolve_keep_mask(nodes_df, property_column, keep_values, exclude_values)

    pruned_nodes_df = nodes_df[keep_mask].reset_index(drop=True)
    kept_ids = set(pruned_nodes_df["content_id"])
    dropped_ids = set(nodes_df["content_id"]) - kept_ids

    if not reconnect_through_pruned or not dropped_ids:
        return _prune_without_reconnect(edges_df, kept_ids), pruned_nodes_df

    return _prune_with_reconnect(edges_df, kept_ids, dropped_ids), pruned_nodes_df


EXCLUDE_EDGE_TYPES = {
    "organisations",
    "primary_publishing_organisation",
    "original_primary_publishing_organisation",
    "taxons",
    "parent_taxons",
    "topics",
    "sections",
    "government",
    "mainstream_browse_pages",
    "children",
    "second_level_browse_pages",
    "top_level_browse_pages",
    "active_top_level_browse_page",
    "parent",
}


def filter_excluded_edge_types(edges_df: pd.DataFrame) -> pd.DataFrame:
    """Drop tagging/metadata/nav edges before traversal."""
    return edges_df.loc[~edges_df["type"].isin(EXCLUDE_EDGE_TYPES)].reset_index(drop=True)


def content_under_browse_page(browse_page_id: str, edges_df: pd.DataFrame) -> pd.DataFrame:
    """
    All real content tagged under a browse page.

    Reverse lookup: mainstream_browse_pages is stored content -> browse page,
    so we filter on target_content_id (the browse page), not source_content_id.
    """
    return (
        edges_df.loc[
            (edges_df["target_content_id"] == browse_page_id)
            & (edges_df["type"] == "mainstream_browse_pages"),
            ["source_content_id", "source_base_path"],
        ]
        .drop_duplicates()
        .reset_index(drop=True)
    )


def build_life_event_subgraph(
    browse_page_id: str,
    edges_df: pd.DataFrame,
    nodes_df: pd.DataFrame,
    max_hop_depth: int = 1,
    exclude_document_types: list[str] | None = None,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """
    End-to-end: discover seeds under a browse page, expand one bounded hop
    outward over real content edges, prune by document_type, return the
    resulting (nodes_df, edges_df) subgraph.

    max_hop_depth: bounds the forward crawl from each seed. Deliberately
        kept small (default 1) so the subgraph stays a reviewable,
        deliberate scope rather than growing back into the whole site.
    exclude_document_types: defaults to ['redirect', 'gone'] if not given.
        Uses reconnect_through_pruned=True, so removing e.g. a redirect
        doesn't sever the real content on either side of it.
    """
    tagged = content_under_browse_page(browse_page_id, edges_df)
    seeds = set(tagged["source_content_id"])
    print(f"{len(seeds)} pages tagged under browse page {browse_page_id}")

    clean_edges_df = filter_excluded_edge_types(edges_df)
    reachable_edges_df = dedupe_edges(
        pd.concat(
            [crawl_graph_local(clean_edges_df, seed, max_depth=max_hop_depth) for seed in seeds],
            ignore_index=True,
        )
    )
    print(f"{len(reachable_edges_df)} edges after one bounded hop from {len(seeds)} seeds")

    node_ids = all_node_ids_from_edges(reachable_edges_df) | seeds
    graph_nodes_df = nodes_df[nodes_df["content_id"].isin(node_ids)].reset_index(drop=True)
    print(f"{len(graph_nodes_df)} nodes before document_type pruning")

    pruned_edges_df, pruned_nodes_df = prune_graph_by_property(
        reachable_edges_df,
        graph_nodes_df,
        property_column="document_type",
        exclude_values=exclude_document_types or ["redirect", "gone"],
        reconnect_through_pruned=True,
    )
    print(f"{len(pruned_nodes_df)} nodes, {len(pruned_edges_df)} edges after pruning")

    return pruned_nodes_df, pruned_edges_df


def compare_to_known_paths(pruned_nodes_df: pd.DataFrame, known_paths: set[str]) -> dict:
    """Post-hoc comparison only — service-graph never touches subgraph
    construction, just this evaluation step at the end."""
    discovered = set(pruned_nodes_df["base_path"])
    return {
        "recovered": known_paths & discovered,
        "missing": known_paths - discovered,
    }
