"""
Pipeline reports: funnel, validation, coverage, diff

Generates Markdown reports that summarise the output of each pipeline run.
All functions write to a caller-supplied output_path.

Key functions:
- generate_funnel_report(sentences_count, candidates_count, sections_called, ...)
      Writes funnel.md: sentence → candidate → section → draft → task counts,
      broken down by page.  Accepts optional stage3_summary and reconcile_summary
      dicts to add stage-specific detail.
- generate_validation_report(drafts_with_errors, tasks_with_errors, output_path)
      Writes validation.md: per-draft and per-task errors and warnings, grouped
      by ID.
- generate_coverage_report(candidates_with_keep_y, tasks, output_path)
      Writes coverage.md: keep=Y action/deadline candidates not cited by any
      final task, grouped by page.
- generate_diff_report(tasks, baseline_path, output_path)
      Writes diff.md: table of all tasks with window summary.  Baseline comparison
      is scaffolded but not yet implemented (M2).

Called by scripts/task_inventory/run_pipeline.py at the end of the pipeline run.
No LLM calls, no file-path assumptions beyond the output_path argument.
"""

from collections import defaultdict
from pathlib import Path

from src.task_inventory.schema import Draft, TaskRecord


def generate_funnel_report(
    sentences_count: int,
    candidates_count: int,
    sections_called: int,
    sections_skipped: int,
    drafts: list[Draft],
    tasks: list[TaskRecord],
    output_path: str | Path,
    *,
    rejected_records: list[dict] | None = None,
    stage3_summary: dict | None = None,
    reconcile_summary: dict | None = None,
) -> None:
    """
    Generate funnel.md showing sentence → candidate → section → draft → task progression.

    For M1: simplified version, just overall counts.
    """
    ok_drafts = [d for d in drafts if d.status == "ok"]
    rejected_records = rejected_records or []
    stage3_summary = stage3_summary or {}
    reconcile_summary = reconcile_summary or {}

    multi_source = sum(1 for t in tasks if len(t.sources) > 1)
    lines = [
        "# Funnel Report\n\n",
        "## Overall\n\n",
        f"- Sentences: {sentences_count}\n",
        f"- Candidates (keep=Y): {candidates_count}\n",
        f"- Sections called: {stage3_summary.get('sections_called', sections_called)}\n",
        f"- Sections excluded by scope: {stage3_summary.get('sections_excluded', 'n/a')}\n",
        f"- Sections skipped (no keep=Y): {stage3_summary.get('sections_skipped', sections_skipped)}\n",
        f"- Drafts OK: {len(ok_drafts)}\n",
        f"- Drafts rejected: {len(rejected_records)}"
        f" (invalid drafts: {sum(r.get('reason') == 'invalid_draft' for r in rejected_records)},"
        f" failed section calls: {sum(r.get('reason') == 'call_failed' for r in rejected_records)})\n",
    ]
    if reconcile_summary:
        lines += [
            f"- Drafts merged automatically as near-duplicates: {reconcile_summary.get('premerged_drafts', 0)}\n",
            f"- Groups clustered: {reconcile_summary.get('groups', 'n/a')}\n",
            f"- Clusters: {reconcile_summary.get('clusters', 'n/a')}"
            f" (single-draft: {reconcile_summary.get('single_draft_clusters', 'n/a')})\n",
            f"- Exactly-once repairs: {len(reconcile_summary.get('exactly_once_notes', []))}\n",
        ]
    lines += [
        f"- Final tasks: {len(tasks)} (built from more than one draft: {multi_source})\n",
        f"- Tasks needing review: {sum(1 for t in tasks if t.status == 'needs_review')}\n",
        f"- Tasks with window: {sum(1 for t in tasks if t.window)}\n",
        f"- Tasks with duration: {sum(1 for t in tasks if t.duration)}\n",
    ]
    if stage3_summary.get("sections_with_rejections"):
        lines.append("\n### Sections with rejected drafts\n\n")
        lines += [f"- {sec}\n" for sec in stage3_summary["sections_with_rejections"]]
    lines.append("\n## By Page\n\n")

    # Group by page
    drafts_by_page = defaultdict(list)
    for draft in ok_drafts:
        drafts_by_page[draft.source.base_path].append(draft)

    tasks_by_page = defaultdict(list)
    for task in tasks:
        # Get pages from sources
        pages = {s.base_path for s in task.sources}
        for page in pages:
            tasks_by_page[page].append(task)

    all_pages = sorted(set(drafts_by_page.keys()) | set(tasks_by_page.keys()))

    rejected_by_page = defaultdict(int)
    for r in rejected_records:
        rejected_by_page[r["source"]["base_path"]] += 1
    all_pages = sorted(set(all_pages) | set(rejected_by_page))

    lines.append("| Page | Drafts | Rejected | Tasks | Tasks w/ window |\n")
    lines.append("|------|--------|----------|-------|----------------|\n")

    for page in all_pages:
        n_drafts = len(drafts_by_page[page])
        page_tasks = tasks_by_page[page]
        n_tasks = len(page_tasks)
        n_with_window = sum(1 for t in page_tasks if t.window)

        lines.append(
            f"| {page} | {n_drafts} | {rejected_by_page[page]} | {n_tasks} | {n_with_window} |\n"
        )

    with open(output_path, "w") as f:
        f.writelines(lines)


def generate_validation_report(
    drafts_with_errors: list[tuple[Draft, list[str], list[str]]],  # (draft, errors, warnings)
    tasks_with_errors: list[tuple[TaskRecord, list[str], list[str]]],  # (task, errors, warnings)
    output_path: str | Path,
) -> None:
    """
    Generate validation.md with all errors and warnings.
    """
    lines = ["# Validation Report\n\n"]

    if drafts_with_errors:
        lines.append("## Draft Validation Issues\n\n")
        for draft, errors, warnings in drafts_with_errors:
            if errors or warnings:
                lines.append(f"### {draft.draft_id}: {draft.title}\n\n")
                lines.append(
                    f"**Page:** {draft.source.base_path} > {draft.source.section_path}\n\n"
                )

                if errors:
                    lines.append("**Errors:**\n")
                    for err in errors:
                        lines.append(f"- {err}\n")
                    lines.append("\n")

                if warnings:
                    lines.append("**Warnings:**\n")
                    for warn in warnings:
                        lines.append(f"- {warn}\n")
                    lines.append("\n")

    if tasks_with_errors:
        lines.append("## Task Validation Issues\n\n")
        for task, errors, warnings in tasks_with_errors:
            if errors or warnings:
                lines.append(f"### {task.id}: {task.title}\n\n")

                if errors:
                    lines.append("**Errors:**\n")
                    for err in errors:
                        lines.append(f"- {err}\n")
                    lines.append("\n")

                if warnings:
                    lines.append("**Warnings:**\n")
                    for warn in warnings:
                        lines.append(f"- {warn}\n")
                    lines.append("\n")

    if not drafts_with_errors and not tasks_with_errors:
        lines.append("No validation issues found.\n")

    with open(output_path, "w") as f:
        f.writelines(lines)


def generate_coverage_report(
    candidates_with_keep_y: list[dict],  # {evidence_id, label, text, page}
    tasks: list[TaskRecord],
    output_path: str | Path,
) -> None:
    """
    Generate coverage.md showing uncited keep=Y candidates.

    Focus on action and deadline candidates that no final task cites.
    """
    # Collect all evidence cited by tasks
    cited_evidence = set()
    for task in tasks:
        cited_evidence.update(task.evidence)

    # Find uncited action/deadline candidates
    uncited = []
    for cand in candidates_with_keep_y:
        if cand["evidence_id"] not in cited_evidence:
            label = cand.get("label", "")
            if "action" in label or "deadline" in label:
                uncited.append(cand)

    # Group by page
    from collections import defaultdict

    by_page = defaultdict(list)
    for cand in uncited:
        by_page[cand["page"]].append(cand)

    lines = ["# Coverage Report\n\n"]
    lines.append("## Uncited Keep=Y Candidates\n\n")
    lines.append(f"Total uncited action/deadline candidates: {len(uncited)}\n\n")

    if not uncited:
        lines.append("All action and deadline candidates are cited by final tasks.\n")
    else:
        for page in sorted(by_page.keys()):
            lines.append(f"### {page}\n\n")
            for cand in by_page[page]:
                label = cand.get("label", "unknown")
                text = cand["text"][:100] + "..." if len(cand["text"]) > 100 else cand["text"]
                lines.append(f"- `{cand['evidence_id']}` ({label}): {text}\n")
            lines.append("\n")

    with open(output_path, "w") as f:
        f.writelines(lines)


def generate_diff_report(
    tasks: list[TaskRecord], baseline_path: str | Path | None, output_path: str | Path
) -> None:
    """
    Generate diff.md comparing this run with baseline.

    For M1: just list tasks and their windows.
    """
    lines = ["# Diff Report\n\n"]

    if baseline_path:
        lines.append(f"**Baseline:** {baseline_path}\n\n")
    else:
        lines.append("**No baseline provided.**\n\n")

    lines.append("## Tasks in This Run\n\n")
    lines.append("| ID | Title | Actor | Phase | Window |\n")
    lines.append("|----|-------|-------|-------|--------|\n")

    for task in tasks:
        window_str = ""
        if task.window:
            parts = []
            if task.window.opens:
                w = task.window.opens
                sign = "+" if w.offset >= 0 else ""
                parts.append(f"op:{w.anchor}{sign}{w.offset}{w.unit[0]}")
            if task.window.closes:
                w = task.window.closes
                sign = "+" if w.offset >= 0 else ""
                parts.append(f"cl:{w.anchor}{sign}{w.offset}{w.unit[0]}")
            window_str = " & ".join(parts)

        lines.append(f"| {task.id} | {task.title} | {task.actor} | {task.phase} | {window_str} |\n")

    # TODO: Compare with baseline (M2)

    with open(output_path, "w") as f:
        f.writelines(lines)
