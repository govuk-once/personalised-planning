"""
Stage 4: Reconcile

Three-step process that turns a flat list of Draft objects into final TaskRecords:
  4a (blocking.py)   — near-duplicate pre-merge + policy-family grouping.
  4b (clustering.py) — LLM decides which drafts in each group belong together.
  4c (merge.py)      — deterministic field-level merge of each cluster.

Public API (re-exported for convenience):
- group_drafts(drafts)              → list[list[Draft]]
- premerge_near_duplicates(drafts)  → (representatives, followers)
- cluster_group(drafts)             → ClusterResult
- enforce_exactly_once(results, ...) → (results, notes)
- expand_followers(results, followers) → results
- merge_cluster(cluster, drafts_by_id, existing_ids) → (TaskRecord, conflicts)
"""

from .blocking import group_drafts
from .clustering import cluster_group
from .merge import merge_cluster

__all__ = ["group_drafts", "cluster_group", "merge_cluster"]
