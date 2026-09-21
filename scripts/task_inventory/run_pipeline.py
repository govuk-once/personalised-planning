"""
Task Extraction Pipeline

Initial implementation of identifying a long list of tasks using pattern based and LLM parsing of GOV.UK
content, followed by human and LLM review.
"""

import argparse
import json
from datetime import datetime
from pathlib import Path

from src.task_inventory.candidates import flag_candidates_from_sentences
from src.task_inventory.checks import check_draft, check_task, check_task_ids_unique
from src.task_inventory.drafts import run_section_drafts
from src.task_inventory.reconcile.blocking import group_drafts, premerge_near_duplicates
from src.task_inventory.reconcile.clustering import (
    cluster_group,
    enforce_exactly_once,
    expand_followers,
)
from src.task_inventory.reconcile.merge import merge_cluster
from src.task_inventory.reports import (
    generate_diff_report,
    generate_funnel_report,
    generate_validation_report,
)
from src.task_inventory.review import (
    generate_clusters_csv,
    generate_conflicts_csv,
    generate_drafts_review_csv,
)
from src.task_inventory.schema import Draft, TaskRecord
from src.task_inventory.sections import extract_sections_from_subgraph


def load_drafts(drafts_path: Path) -> list[Draft]:
    """Load drafts from JSONL file"""
    drafts = []
    with open(drafts_path) as f:
        for line in f:
            if line.strip():
                draft_data = json.loads(line)
                drafts.append(Draft.model_validate(draft_data))
    return drafts


def load_rejected(rejected_path: Path) -> list[dict]:
    """Load rejected draft records (dicts) from JSONL, if the file exists"""
    if not rejected_path.exists():
        return []
    with open(rejected_path) as f:
        return [json.loads(line) for line in f if line.strip()]


def load_json(path: Path) -> dict:
    if not path.exists():
        return {}
    with open(path) as f:
        return json.load(f)


def load_evidence_texts(sentences_path: str) -> dict[str, str]:
    """Load evidence_id -> text mapping"""
    import pandas as pd

    df = pd.read_csv(sentences_path)
    return dict(zip(df["evidence_id"], df["text"], strict=False))


def run_sections_stage(args):
    """Stage 0-1: Section extraction"""
    print(f"\n{'=' * 80}")
    print("Running Stage 0-1: Section Extraction")
    print(f"{'=' * 80}\n")

    extract_sections_from_subgraph(subgraph_path=args.subgraph, output_path=args.sentences)

    print(f"\n✓ Stage 0-1 complete. Output: {args.sentences}")


def run_candidates_stage(args):
    """Stage 2: Candidate flagging"""
    print(f"\n{'=' * 80}")
    print("Running Stage 2: Candidate Flagging")
    print(f"{'=' * 80}\n")

    # Handle pattern-only flag
    use_llm = not getattr(args, "pattern_only", False)

    flag_candidates_from_sentences(
        sentences_path=args.sentences,
        output_path=args.candidates,
        use_llm=use_llm,
        model_id=getattr(args, "model_id", "eu.anthropic.claude-sonnet-4-6"),
        region=getattr(args, "region", "eu-west-2"),
    )

    print(f"\n✓ Stage 2 complete. Output: {args.candidates}")


def run_drafts_stage(args):
    """Stage 3: Section drafts"""
    print(f"\n{'=' * 80}")
    print("Running Stage 3: Section Drafts")
    print(f"{'=' * 80}\n")

    output_dir = args.output_dir or f"data/runs/{datetime.now().strftime('%Y%m%d_%H%M%S')}"
    Path(output_dir).mkdir(parents=True, exist_ok=True)

    pages = None
    if args.pages:
        pages = [p if p.startswith("/") else f"/{p}" for p in args.pages]
        print(f"Filtering to pages: {pages}\n")

    run_section_drafts(
        sentences_path=args.sentences,
        candidates_path=args.candidates,
        output_dir=output_dir,
        pages=pages,
        model_id=args.model_id,
        region=args.region,
    )

    print(f"\n✓ Stage 3 complete. Output in {output_dir}")

    return output_dir


def run_reconcile_stage(args):
    """
    Stage 4: Reconcile (near-duplicate pre-merge, grouping, clustering, merging)

    Reads drafts from --from-run. Unless --output-dir is given, writes to a NEW run folder
    (the source run is never overwritten) and copies the draft files there, so that
    `validate --from-run <new folder>` works.
    """
    import shutil

    print(f"\n{'=' * 80}")
    print("Running Stage 4: Reconcile")
    print(f"{'=' * 80}\n")

    run_dir = Path(args.from_run or "data/runs/latest")
    drafts_path = run_dir / "drafts.jsonl"

    if not drafts_path.exists():
        print(f"Error: {drafts_path} not found. Run drafts stage first.")
        return None

    if args.output_dir:
        output_dir = Path(args.output_dir)
    else:
        output_dir = Path(f"data/runs/{datetime.now().strftime('%Y%m%d_%H%M%S')}_reconcile")
    output_dir.mkdir(parents=True, exist_ok=True)

    if output_dir.resolve() != run_dir.resolve():
        for name in ("drafts.jsonl", "drafts_rejected.jsonl", "stage3_summary.json"):
            if (run_dir / name).exists():
                shutil.copy2(run_dir / name, output_dir / name)

    print(f"Loading drafts from {drafts_path}")
    drafts = load_drafts(drafts_path)
    ok_drafts = [d for d in drafts if d.status == "ok"]
    print(f"Loaded {len(ok_drafts)} OK drafts\n")

    # Stage 4a-0: near-duplicate pre-merge (code only)
    representatives, followers = premerge_near_duplicates(ok_drafts)
    n_followers = sum(len(v) for v in followers.values())
    print(
        f"Near-duplicate pre-merge: {n_followers} drafts merged into {len(followers)} representatives"
    )

    # Stage 4a: Grouping (each draft in exactly one group)
    print("Stage 4a: Grouping drafts...")
    groups = group_drafts(representatives)
    print(f"Created {len(groups)} groups\n")

    # Stage 4b: Clustering
    print("Stage 4b: Clustering groups...")
    all_cluster_results = []
    for i, group in enumerate(groups, 1):
        policies = sorted({d.policy for d in group})
        print(f"\nGroup {i}/{len(groups)}: {len(group)} drafts")
        print(f"  Policies: {', '.join(policies)}")

        cluster_result = cluster_group(group, model_id=args.model_id, region=args.region)
        all_cluster_results.append(cluster_result)
        print(f"  → {len(cluster_result.clusters)} clusters")

    # Every representative must be in exactly one cluster (safety net across groups)
    all_cluster_results, exactly_once_notes = enforce_exactly_once(
        all_cluster_results, representatives
    )
    if exactly_once_notes:
        print(f"\n⚠️  Exactly-once repairs across groups: {len(exactly_once_notes)}")
        for note in exactly_once_notes[:10]:
            print(f"  - {note}")

    # Put pre-merged near-duplicates back into their representative's cluster
    all_cluster_results = expand_followers(all_cluster_results, followers)

    # Final check on the full set of drafts
    member_ids = [m.draft_id for r in all_cluster_results for c in r.clusters for m in c.members]
    assert len(member_ids) == len(set(member_ids)) == len(ok_drafts), (
        f"exactly-once violated after expansion: {len(member_ids)} memberships, "
        f"{len(set(member_ids))} unique, {len(ok_drafts)} drafts"
    )

    # Stage 4c: Merging
    print("\nStage 4c: Merging clusters...")
    drafts_by_id = {d.draft_id: d for d in ok_drafts}

    all_tasks = []
    all_conflicts = []
    existing_ids = set()

    for cluster_result in all_cluster_results:
        for cluster in cluster_result.clusters:
            try:
                task, conflicts = merge_cluster(cluster, drafts_by_id, existing_ids)
            except AssertionError as e:
                print(f"  ✗ Merge failed for cluster {cluster.key}: {e}")
                raise  # nothing-lost check failed - fatal
            all_tasks.append(task)
            existing_ids.add(task.id)
            # One row per conflicting field, so each can be resolved separately
            for conflict in conflicts:
                all_conflicts.append(
                    {"task_id": task.id, "conflicts": conflict, "task_title": task.title}
                )

    clusters_total = sum(len(r.clusters) for r in all_cluster_results)
    single = sum(1 for r in all_cluster_results for c in r.clusters if len(c.members) == 1)
    print(
        f"\n✓ Created {len(all_tasks)} tasks from {len(ok_drafts)} drafts "
        f"({clusters_total} clusters, {single} with a single draft)"
    )
    if all_conflicts:
        print(f"⚠️  {len({c['task_id'] for c in all_conflicts})} tasks have conflicts")

    tasks_path = output_dir / "tasks.json"
    with open(tasks_path, "w") as f:
        json.dump([t.model_dump() for t in all_tasks], f, indent=2)
    print(f"\nSaved {tasks_path}")

    clusters_csv_path = output_dir / "clusters.csv"
    generate_clusters_csv(all_cluster_results, drafts_by_id, clusters_csv_path)
    print(f"Saved {clusters_csv_path}")

    if all_conflicts:
        conflicts_csv_path = output_dir / "conflicts.csv"
        generate_conflicts_csv(all_conflicts, conflicts_csv_path)
        print(f"Saved {conflicts_csv_path}")

    summary = {
        "from_run": str(run_dir),
        "created": datetime.now().isoformat(timespec="seconds"),
        "drafts": len(ok_drafts),
        "premerged_drafts": n_followers,
        "premerged_sets": dict(followers),
        "groups": len(groups),
        "clusters": clusters_total,
        "single_draft_clusters": single,
        "tasks": len(all_tasks),
        "tasks_with_conflicts": len({c["task_id"] for c in all_conflicts}),
        "exactly_once_notes": exactly_once_notes,
    }
    with open(output_dir / "reconcile_summary.json", "w") as f:
        json.dump(summary, f, indent=2)

    print(f"\n✓ Stage 4 complete. Output in {output_dir}")

    return str(output_dir)


def run_validate_stage(args):
    """Stage 5: Validate and generate reports"""
    print(f"\n{'=' * 80}")
    print("Running Stage 5: Validate")
    print(f"{'=' * 80}\n")

    # Load data
    run_dir = Path(args.from_run or "data/runs/latest")
    drafts_path = run_dir / "drafts.jsonl"
    tasks_path = run_dir / "tasks.json"

    if not tasks_path.exists():
        print(f"Error: {tasks_path} not found. Run reconcile stage first.")
        return None

    print(f"Loading from {run_dir}")
    drafts = load_drafts(drafts_path)
    ok_drafts = [d for d in drafts if d.status == "ok"]

    with open(tasks_path) as f:
        tasks_data = json.load(f)
    tasks = [TaskRecord.model_validate(t) for t in tasks_data]

    # Load evidence texts
    evidence_texts = load_evidence_texts(args.sentences)

    print(f"Loaded {len(ok_drafts)} drafts, {len(tasks)} tasks\n")

    # Validate drafts
    print("Validating drafts...")
    drafts_with_issues = []
    for draft in ok_drafts:
        errors, warnings = check_draft(draft, evidence_texts)
        if errors or warnings:
            drafts_with_issues.append((draft, errors, warnings))

    # Validate tasks
    print("Validating tasks...")
    tasks_with_issues = []
    for task in tasks:
        errors, warnings = check_task(task, evidence_texts)
        if errors or warnings:
            tasks_with_issues.append((task, errors, warnings))

    # Check ID uniqueness
    id_errors = check_task_ids_unique(tasks)
    if id_errors:
        print("\n✗ ID uniqueness errors:")
        for err in id_errors:
            print(f"  - {err}")

    # Count errors
    total_errors = sum(len(e) for _, e, _ in drafts_with_issues + tasks_with_issues) + len(
        id_errors
    )
    total_warnings = sum(len(w) for _, _, w in drafts_with_issues + tasks_with_issues)

    print("\nValidation complete:")
    print(f"  Errors: {total_errors}")
    print(f"  Warnings: {total_warnings}")

    # Generate reports
    output_dir = Path(args.output_dir) if args.output_dir else run_dir

    print("\nGenerating reports...")

    # Get counts for funnel
    import pandas as pd

    sentences_df = pd.read_csv(args.sentences)
    candidates_df = pd.read_csv(args.candidates)

    if args.pages:
        pages = [p if p.startswith("/") else f"/{p}" for p in args.pages]
        sentences_df = sentences_df[sentences_df["base_path"].isin(pages)]
        candidates_df = candidates_df[candidates_df["page"].isin(pages)]

    sentences_count = len(sentences_df)
    candidates_count = len(candidates_df[candidates_df["keep"] == "Y"])

    rejected_records = load_rejected(run_dir / "drafts_rejected.jsonl")
    stage3_summary = load_json(run_dir / "stage3_summary.json")
    reconcile_summary = load_json(run_dir / "reconcile_summary.json")

    # Fallback counts if the stage 3 summary is missing: count (page, section) pairs
    sections_called = len({(d.source.base_path, d.source.section_path) for d in ok_drafts})
    sections_skipped = 0

    # Funnel report
    funnel_path = output_dir / "funnel.md"
    generate_funnel_report(
        sentences_count,
        candidates_count,
        sections_called,
        sections_skipped,
        drafts,
        tasks,
        funnel_path,
        rejected_records=rejected_records,
        stage3_summary=stage3_summary,
        reconcile_summary=reconcile_summary,
    )
    print(f"  {funnel_path}")

    # Validation report
    validation_path = output_dir / "validation.md"
    generate_validation_report(drafts_with_issues, tasks_with_issues, validation_path)
    print(f"  {validation_path}")

    # Diff report
    diff_path = output_dir / "diff.md"
    generate_diff_report(tasks, args.baseline, diff_path)
    print(f"  {diff_path}")

    # Coverage report
    from src.task_inventory.reports import generate_coverage_report

    keep_y_candidates = []
    for _, row in candidates_df[candidates_df["keep"] == "Y"].iterrows():
        keep_y_candidates.append(
            {
                "evidence_id": row["evidence_id"],
                "label": row.get("labels", "") if isinstance(row.get("labels", ""), str) else "",
                "text": str(row.get("text", row.get("snippet_text", ""))),
                "page": row["page"],
            }
        )

    coverage_path = output_dir / "coverage.md"
    generate_coverage_report(keep_y_candidates, tasks, coverage_path)
    print(f"  {coverage_path}")

    # Drafts review CSV
    drafts_review_path = output_dir / "drafts_review.csv"
    generate_drafts_review_csv(ok_drafts, drafts_review_path)
    print(f"  {drafts_review_path}")

    print("\n✓ Stage 5 complete")

    if total_errors > 0:
        print(f"\n⚠️  Run has {total_errors} errors")
        return None

    return str(output_dir)


def run_all_stages(args):
    """Run all stages in sequence"""
    # Stage 0-1: Sections (if not skipped)
    if not args.skip_sections:
        run_sections_stage(args)

    # Stage 2: Candidates (if not skipped)
    if not args.skip_candidates:
        run_candidates_stage(args)

    # Stage 3: Drafts
    output_dir = run_drafts_stage(args)

    # Update args to use the output dir
    args.from_run = output_dir

    # Stage 4: Reconcile (writes into output_dir if given, otherwise a new folder)
    args.output_dir = args.output_dir or output_dir
    reconcile_dir = run_reconcile_stage(args)
    if reconcile_dir:
        args.from_run = reconcile_dir

    # Stage 5: Validate
    run_validate_stage(args)


def main():
    parser = argparse.ArgumentParser(description="Task Extraction Pipeline V3")

    subparsers = parser.add_subparsers(dest="command", help="Pipeline stage to run")

    # Sections command
    sections_parser = subparsers.add_parser("sections", help="Stage 0-1: Extract sections")
    sections_parser.add_argument("--subgraph", default="data/having_a_baby_subgraph.json")
    sections_parser.add_argument("--sentences", default="data/sentences.csv")

    # Candidates command
    candidates_parser = subparsers.add_parser("candidates", help="Stage 2: Flag candidates")
    candidates_parser.add_argument("--sentences", default="data/sentences.csv")
    candidates_parser.add_argument("--candidates", default="data/candidates.csv")
    candidates_parser.add_argument(
        "--pattern-only",
        action="store_true",
        help="Pattern matching only (no LLM, default is pattern + LLM)",
    )
    candidates_parser.add_argument("--model-id", default="eu.anthropic.claude-sonnet-4-0")
    candidates_parser.add_argument("--region", default="eu-west-2")

    # Drafts command
    drafts_parser = subparsers.add_parser("drafts", help="Stage 3: Generate section drafts")
    drafts_parser.add_argument("--sentences", default="data/sentences.csv")
    drafts_parser.add_argument("--candidates", default="data/candidates.csv")
    drafts_parser.add_argument("--output-dir")
    drafts_parser.add_argument("--pages", nargs="+", help="Filter to specific pages")
    drafts_parser.add_argument("--model-id")
    drafts_parser.add_argument("--region")

    # Reconcile command
    reconcile_parser = subparsers.add_parser("reconcile", help="Stage 4: Cluster and merge drafts")
    reconcile_parser.add_argument("--from-run", help="Run directory with drafts.jsonl")
    reconcile_parser.add_argument("--output-dir")
    reconcile_parser.add_argument("--model-id")
    reconcile_parser.add_argument("--region")

    # Validate command
    validate_parser = subparsers.add_parser("validate", help="Stage 5: Validate and report")
    validate_parser.add_argument("--from-run", help="Run directory with tasks.json")
    validate_parser.add_argument("--sentences", default="data/sentences.csv")
    validate_parser.add_argument("--candidates", default="data/candidates.csv")
    validate_parser.add_argument("--output-dir")
    validate_parser.add_argument("--baseline", help="Baseline tasks.json for diff")
    validate_parser.add_argument(
        "--pages", nargs="+", help="Pages filter (must match drafts stage)"
    )

    # All command
    all_parser = subparsers.add_parser("all", help="Run all stages (0-5)")
    all_parser.add_argument("--subgraph", default="data/having_a_baby_subgraph.json")
    all_parser.add_argument("--sentences", default="data/sentences.csv")
    all_parser.add_argument("--candidates", default="data/candidates.csv")
    all_parser.add_argument("--output-dir")
    all_parser.add_argument("--pages", nargs="+", help="Filter to specific pages")
    all_parser.add_argument("--baseline", help="Baseline tasks.json for diff")
    all_parser.add_argument("--model-id", default="eu.anthropic.claude-sonnet-4-0")
    all_parser.add_argument("--region", default="eu-west-2")
    all_parser.add_argument(
        "--skip-sections",
        action="store_true",
        help="Skip section extraction (use existing sentences.csv)",
    )
    all_parser.add_argument(
        "--skip-candidates",
        action="store_true",
        help="Skip candidate flagging (use existing candidates.csv)",
    )
    all_parser.add_argument(
        "--pattern-only", action="store_true", help="Pattern matching only for candidates (no LLM)"
    )

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        return

    if args.command == "sections":
        run_sections_stage(args)
    elif args.command == "candidates":
        run_candidates_stage(args)
    elif args.command == "drafts":
        run_drafts_stage(args)
    elif args.command == "reconcile":
        run_reconcile_stage(args)
    elif args.command == "validate":
        run_validate_stage(args)
    elif args.command == "all":
        run_all_stages(args)


if __name__ == "__main__":
    main()
