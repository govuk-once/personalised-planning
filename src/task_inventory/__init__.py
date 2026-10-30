"""
Task Extraction Pipeline V3  —  public API

Exposes the models, vocabularies, and stage functions needed by external callers
(primarily scripts/task_inventory/run_pipeline.py).

Pipeline stages:
    Stage 0-1  sections.extract_sections_from_subgraph   subgraph → sentences.csv
    Stage 2    candidates.flag_candidates_from_sentences  sentences → candidates.csv
    Stage 3    drafts.run_section_drafts                  candidates → drafts.jsonl
    Stage 4a   reconcile.group_drafts                     drafts → groups
    Stage 4a   reconcile.premerge_near_duplicates         groups → representatives + followers
    Stage 4b   reconcile.cluster_group                    group → ClusterResult
    Stage 4b   reconcile.enforce_exactly_once             all results → repaired results
    Stage 4b   reconcile.expand_followers                 followers re-added to clusters
    Stage 4c   reconcile.merge_cluster                    cluster + drafts → TaskRecord
    Stage 5    checks.check_task / check_task_ids_unique  validation
               reports.*                                  Markdown report generation

Re-exported names are in __all__ below.
"""

from .checks import check_draft, check_task, check_task_ids_unique
from .drafts import run_section_drafts
from .reconcile import cluster_group, group_drafts, merge_cluster
from .schema import (
    Actor,
    Anchor,
    Cluster,
    ClusterResult,
    Draft,
    Duration,
    Journey,
    Member,
    Method,
    Phase,
    Policy,
    SectionDrafts,
    Source,
    TaskBody,
    TaskRecord,
    Unit,
    Window,
    WindowEnd,
)

__all__ = [
    # Models
    "Draft",
    "TaskRecord",
    "TaskBody",
    "SectionDrafts",
    "ClusterResult",
    "Cluster",
    "Member",
    "Window",
    "WindowEnd",
    "Duration",
    "Source",
    # Vocabularies
    "Actor",
    "Method",
    "Anchor",
    "Unit",
    "Phase",
    "Journey",
    "Policy",
    # Functions
    "run_section_drafts",
    "group_drafts",
    "cluster_group",
    "merge_cluster",
    "check_draft",
    "check_task",
    "check_task_ids_unique",
]
