"""
Review CSV generation

Produces human-readable CSV snapshots at each review gate so that a person can
inspect and annotate pipeline outputs without needing to read JSONL files directly.

Key functions:
- generate_drafts_review_csv(drafts, output_path)
      Writes drafts_review.csv after stage 3.
      Columns: draft_id, page, section_path, title, actor, phase, journeys,
      window (compact), duration (compact), n_sub_tasks, status, errors.
- generate_clusters_csv(cluster_result, drafts_by_id, output_path)
      Writes clusters.csv after stage 4b (clustering), showing which drafts were
      grouped together and under what canonical title.
- generate_conflicts_csv(conflicts, output_path)
      Writes conflicts.csv listing fields where merged drafts disagreed.

Called by scripts/task_inventory/run_pipeline.py after each stage that produces reviewable output.
No LLM calls, no file-path assumptions beyond the output_path argument.
"""

from pathlib import Path

import pandas as pd

from src.task_inventory.schema import Draft


def generate_drafts_review_csv(drafts: list[Draft], output_path: str | Path) -> None:
    """
    Generate drafts_review.csv for review 2.

    Columns: draft_id, page, section_path, title, actor, phase, journeys,
             window_summary, duration_summary, n_sub_tasks, status, errors
    """
    rows = []

    for draft in drafts:
        window_summary = ""
        if draft.window:
            parts = []
            if draft.window.opens:
                w = draft.window.opens
                sign = "+" if w.offset >= 0 else ""
                parts.append(f"op:{w.anchor}{sign}{w.offset}{w.unit[0]}")
            if draft.window.closes:
                w = draft.window.closes
                sign = "+" if w.offset >= 0 else ""
                parts.append(f"cl:{w.anchor}{sign}{w.offset}{w.unit[0]}")
            window_summary = " & ".join(parts)

        duration_summary = ""
        if draft.duration:
            duration_summary = f"{draft.duration.value}{draft.duration.unit[0]}"

        journeys_str = ",".join(draft.journeys)

        rows.append(
            {
                "draft_id": draft.draft_id,
                "page": draft.source.base_path,
                "section_path": draft.source.section_path,
                "title": draft.title,
                "actor": draft.actor,
                "phase": draft.phase,
                "journeys": journeys_str,
                "window": window_summary,
                "duration": duration_summary,
                "n_sub_tasks": len(draft.sub_tasks),
                "status": draft.status,
                "errors": "; ".join(draft.errors) if draft.errors else "",
            }
        )

    df = pd.DataFrame(rows)
    df.to_csv(output_path, index=False)


def generate_clusters_csv(
    cluster_result,  # ClusterResult or list of them
    drafts_by_id: dict[str, Draft],
    output_path: str | Path,
) -> None:
    """
    Generate clusters.csv for review 3.

    Columns: cluster_key, canonical_title, role, parent_draft_id,
             draft_id, draft_title, page, section_path
    """
    rows = []

    # Handle single result or list
    if not isinstance(cluster_result, list):
        cluster_results = [cluster_result]
    else:
        cluster_results = cluster_result

    for result in cluster_results:
        for cluster in result.clusters:
            for member in cluster.members:
                draft = drafts_by_id.get(member.draft_id)
                if not draft:
                    continue

                rows.append(
                    {
                        "cluster_key": cluster.key,
                        "canonical_title": cluster.canonical_title,
                        "role": member.role,
                        "parent_draft_id": member.parent_draft_id or "",
                        "draft_id": member.draft_id,
                        "draft_title": draft.title,
                        "page": draft.source.base_path,
                        "section_path": draft.source.section_path,
                    }
                )

    df = pd.DataFrame(rows)
    df.to_csv(output_path, index=False)


def generate_conflicts_csv(
    conflicts: list[dict],  # List of {task_id, field, values, evidence_text, blocking}
    output_path: str | Path,
) -> None:
    """
    Generate conflicts.csv for review 3.

    Each conflict is a row with task_id, field, conflicting values.
    """
    df = pd.DataFrame(conflicts)
    df.to_csv(output_path, index=False)
