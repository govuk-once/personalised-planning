"""
Stage 4b: Clustering

One LLM call per policy-family group: the model decides which drafts represent
the same citizen task and assigns each a role (primary / same / sub_task).
Results are validated (every draft exactly once, exactly one primary per cluster)
and repaired rather than discarded when validation fails.

Key functions:
- cluster_group(drafts, model_id, region)
      Top-level entry point.  Calls the LLM, validates, retries once with error
      feedback, then repairs the best answer if still invalid.  Falls back to
      singleton clusters (one draft each) only if no response could be parsed.
- check_clustering(result, draft_ids)
      Validates a ClusterResult: coverage, uniqueness, primary count, sub-task
      parent membership.  Returns list of error strings.
- repair_cluster_result(result, draft_ids, titles)
      Applies minimal fixes: remove unknown IDs, deduplicate, promote missing
      primaries, add missing drafts as singletons.
- enforce_exactly_once(results, drafts)
      Cross-group safety net: repairs any draft that leaked into two groups.
- expand_followers(results, followers)
      Re-attaches near-duplicate followers (from blocking.premerge_near_duplicates)
      into their representative's cluster.
- singleton_result(drafts)
      Fallback: each draft becomes its own single-member cluster.

Prompt template:  prompts/clusters.v2.md  (read from CWD at call time).
LLM cache:        data/cache/clusters/<hash16>.json.
Requires AWS Bedrock credentials; model defaults to ANTHROPIC_MODEL env var or
eu.anthropic.claude-sonnet-5.
"""

from pathlib import Path

from src.task_inventory.llm import call_structured, make_cache_key
from src.task_inventory.schema import Cluster, ClusterResult, Draft, Member

PROMPT_VERSION = "v2"
VERB_LIST = [
    "Check",
    "Tell",
    "Give notice",
    "Give",
    "Claim",
    "Apply",
    "Register",
    "Order",
    "Plan",
    "Report",
    "Take",
    "Challenge",
    "Get help",
    "Send",
    "Request",
    "Transfer",
    "Choose",
    "Arrange",
    "Contact",
    "Attend",
    "Opt out",
    "Restart",
    "Complain",
    "Notify",
    "Book",
    "Query",
    "Work out",
    "Use",
]


def load_prompt_template() -> str:
    """Load clustering prompt template"""
    prompt_path = Path(f"prompts/clusters.{PROMPT_VERSION}.md")
    with open(prompt_path) as f:
        return f.read()


def format_draft_line(draft: Draft) -> str:
    """
    Format one draft as a single line for the clustering prompt.

    Format: draft_id | title | actor | phase | page > section | window summary | N sub-tasks
    """
    parts = [draft.draft_id, draft.title, draft.actor, draft.phase]

    # Add page and section
    parts.append(f"{draft.source.base_path} > {draft.source.section_path}")

    # Window summary
    window_parts = []
    if draft.window:
        if draft.window.opens:
            w = draft.window.opens
            sign = "+" if w.offset >= 0 else ""
            window_parts.append(f"op: {w.anchor}{sign}{w.offset}{w.unit[0]}")
        if draft.window.closes:
            w = draft.window.closes
            sign = "+" if w.offset >= 0 else ""
            window_parts.append(f"cl: {w.anchor}{sign}{w.offset}{w.unit[0]}")

    if window_parts:
        parts.append(" & ".join(window_parts))

    # Sub-tasks count
    if draft.sub_tasks:
        parts.append(f"{len(draft.sub_tasks)} sub-tasks")

    return " | ".join(parts)


def build_prompt(drafts: list[Draft]) -> str:
    """Build clustering prompt for one group"""
    template = load_prompt_template()

    draft_lines = []
    for draft in drafts:
        draft_lines.append(format_draft_line(draft))

    drafts_str = "\n".join(draft_lines)

    return template.format(drafts=drafts_str)


def check_clustering(result: ClusterResult, draft_ids: set[str]) -> list[str]:
    """
    Validate clustering result.

    Checks:
    - Every draft appears exactly once (no duplicates, no missing)
    - Each cluster has exactly one primary
    - Every sub_task has a parent in the same cluster
    - Cluster keys are unique
    - Canonical titles start with a verb (warning only)

    Returns:
        List of error messages (empty if OK)
    """
    errors = []

    # Collect all draft IDs from clusters
    seen_ids = []  # Use list to detect duplicates
    cluster_members = {}  # cluster_key -> list of draft_ids
    cluster_keys_seen = set()

    for cluster in result.clusters:
        # Check cluster key uniqueness
        if cluster.key in cluster_keys_seen:
            errors.append(f"Duplicate cluster key: '{cluster.key}'")
        cluster_keys_seen.add(cluster.key)

        cluster_members[cluster.key] = []
        primary_count = 0

        for member in cluster.members:
            # Track every appearance (including duplicates)
            seen_ids.append(member.draft_id)
            cluster_members[cluster.key].append(member.draft_id)

            # Count primaries
            if member.role == "primary":
                primary_count += 1

            # Check sub_task parents
            if member.role == "sub_task":
                if not member.parent_draft_id:
                    errors.append(f"Sub-task member {member.draft_id} has no parent_draft_id")

        # Check exactly one primary
        if primary_count == 0:
            errors.append(f"Cluster '{cluster.key}' has no primary")
        elif primary_count > 1:
            errors.append(
                f"Cluster '{cluster.key}' has {primary_count} primaries (must be exactly 1)"
            )

    # Check for duplicate appearances
    from collections import Counter

    id_counts = Counter(seen_ids)
    duplicates = [draft_id for draft_id, count in id_counts.items() if count > 1]
    if duplicates:
        for draft_id in duplicates:
            errors.append(
                f"Draft {draft_id} appears {id_counts[draft_id]} times (must be exactly once)"
            )

    # Check every input draft appears
    seen_ids_set = set(seen_ids)
    missing = draft_ids - seen_ids_set
    if missing:
        errors.append(f"Drafts not assigned to any cluster: {sorted(missing)}")

    extra = seen_ids_set - draft_ids
    if extra:
        errors.append(f"Unknown draft IDs in clustering result: {sorted(extra)}")

    # Verify sub_task parents exist in same cluster
    for cluster in result.clusters:
        cluster_draft_ids = {m.draft_id for m in cluster.members}
        for member in cluster.members:
            if member.role == "sub_task" and member.parent_draft_id:
                if member.parent_draft_id not in cluster_draft_ids:
                    errors.append(
                        f"Sub-task {member.draft_id} parent {member.parent_draft_id} "
                        + f"not in same cluster '{cluster.key}'"
                    )

    return errors


def _call(prompt: str, system: str, cache_key: str, model_id, region):
    return call_structured(
        ClusterResult,
        prompt=prompt,
        system=system,
        max_tokens=8192,  # large groups can exceed 4096 output tokens
        check=None,  # checked below, so a flawed answer can be repaired, not discarded
        retries=0,
        cache_key=cache_key,
        model_id=model_id,
        region=region,
    )


def cluster_group(
    drafts: list[Draft], *, model_id: str | None = None, region: str | None = None
) -> ClusterResult:
    """
    Cluster one group of drafts.

    1. Call the LLM and check the answer (every draft exactly once, one primary, ...).
    2. If the check fails, retry once with the errors added to the prompt.
    3. If it still fails, REPAIR the better answer (see repair_cluster_result) rather than
       discarding it. Only if no answer could be parsed at all does every draft become its
       own cluster.

    Always returns a result in which every input draft appears exactly once.
    """
    if not drafts:
        return ClusterResult(clusters=[], alternatives=[])

    prompt = build_prompt(drafts)
    draft_ids = {d.draft_id for d in drafts}

    system = """You are grouping draft tasks into clusters.

Each cluster becomes one final task. Group drafts that describe the same action.
Keep distinct actions separate. Mark sub-tasks appropriately.

Every draft must appear exactly once. Every cluster needs exactly one primary."""

    cache_payload = {"draft_ids": [d.draft_id for d in drafts], "titles": [d.title for d in drafts]}
    cache_key = make_cache_key("clusters", PROMPT_VERSION, model_id or "default", cache_payload)

    attempts: list[tuple[ClusterResult, list[str]]] = []

    first = _call(prompt, system, cache_key, model_id, region)
    if first.value:
        errors = check_clustering(first.value, draft_ids)
        if not errors:
            return first.value
        attempts.append((first.value, errors))
        feedback = "\n".join(f"- {e}" for e in errors[:30])
    else:
        feedback = "\n".join(
            f"- {e}" for e in (first.errors or ["response could not be parsed"])[:30]
        )

    retry_prompt = (
        prompt
        + "\n\n## Your previous answer had these errors\n\n"
        + feedback
        + "\n\nReturn a corrected answer for ALL drafts above. "
        "Every draft must appear exactly once, and every cluster needs exactly one primary."
    )
    second = _call(retry_prompt, system, cache_key + "-retry1", model_id, region)
    if second.value:
        errors = check_clustering(second.value, draft_ids)
        if not errors:
            return second.value
        attempts.append((second.value, errors))

    if attempts:
        best, best_errors = min(attempts, key=lambda a: len(a[1]))
        repaired, notes = repair_cluster_result(best, draft_ids)
        print(
            f"  ⚠️  Clustering answer had {len(best_errors)} error(s); repaired: {'; '.join(notes[:5])}"
        )
        return repaired

    print(f"  ⚠️  Clustering failed: {first.errors[0] if first.errors else 'unknown error'}")
    print("  Falling back: each draft becomes its own cluster")
    return singleton_result(drafts)


# ---------------------------------------------------------------------------
# Repair and exactly-once enforcement
# ---------------------------------------------------------------------------


def singleton_result(drafts: list[Draft]) -> ClusterResult:
    return ClusterResult(
        clusters=[
            Cluster(
                key=d.draft_id,
                canonical_title=d.title,
                members=[Member(draft_id=d.draft_id, role="primary", parent_draft_id=None)],
            )
            for d in drafts
        ],
        alternatives=[],
    )


def repair_cluster_result(
    result: ClusterResult,
    draft_ids: set[str],
    titles: dict[str, str] | None = None,
) -> tuple[ClusterResult, list[str]]:
    """
    Make a clustering answer valid with the smallest changes:
    - unknown draft IDs are removed
    - a draft that appears more than once is kept only in its first multi-draft cluster
      (or its first cluster, if all are single-draft)
    - a sub-task whose parent is not in the same cluster becomes 'same'
    - a cluster with no primary gets one (its first member); extra primaries become 'same'
    - empty clusters are removed; duplicate cluster keys get a suffix
    - drafts missing from the answer become their own clusters
    - alternatives that point at removed clusters are dropped

    Returns (repaired_result, notes).
    """
    notes: list[str] = []
    titles = titles or {}

    # Where does each draft appear? Prefer its first appearance in a multi-draft cluster.
    appearances: dict[str, list[int]] = {}
    for ci, cluster in enumerate(result.clusters):
        for m in cluster.members:
            appearances.setdefault(m.draft_id, []).append(ci)

    keep_in: dict[str, int] = {}
    for draft_id, cluster_idxs in appearances.items():
        if draft_id not in draft_ids:
            notes.append(f"removed unknown draft {draft_id}")
            continue
        multi = [ci for ci in cluster_idxs if len(result.clusters[ci].members) > 1]
        keep_in[draft_id] = (multi or cluster_idxs)[0]
        if len(cluster_idxs) > 1:
            notes.append(f"{draft_id} appeared {len(cluster_idxs)} times; kept once")

    new_clusters: list[Cluster] = []
    used_keys: set[str] = set()
    key_map: dict[str, str] = {}

    for ci, cluster in enumerate(result.clusters):
        members = []
        seen_here: set[str] = set()
        for m in cluster.members:
            if keep_in.get(m.draft_id) != ci or m.draft_id in seen_here:
                continue
            seen_here.add(m.draft_id)
            members.append(
                Member(draft_id=m.draft_id, role=m.role, parent_draft_id=m.parent_draft_id)
            )
        if not members:
            continue

        member_ids = {m.draft_id for m in members}
        for m in members:
            if m.role == "sub_task" and m.parent_draft_id not in member_ids:
                notes.append(f"{m.draft_id}: sub-task parent missing, set to 'same'")
                m.role, m.parent_draft_id = "same", None

        primaries = [m for m in members if m.role == "primary"]
        if not primaries:
            candidate = next((m for m in members if m.role == "same"), members[0])
            # A sub-task can't be primary while it has a parent; clear it.
            candidate.role, candidate.parent_draft_id = "primary", None
            notes.append(f"cluster '{cluster.key}': no primary, promoted {candidate.draft_id}")
        for extra in primaries[1:]:
            extra.role = "same"
            notes.append(f"cluster '{cluster.key}': extra primary {extra.draft_id} set to 'same'")

        # Sub-tasks must point at a draft that is not itself a sub-task
        primary_id = next(m.draft_id for m in members if m.role == "primary")
        sub_ids = {m.draft_id for m in members if m.role == "sub_task"}
        for m in members:
            if m.role == "sub_task" and m.parent_draft_id in sub_ids:
                m.parent_draft_id = primary_id

        key = cluster.key
        n = 2
        while key in used_keys:
            key = f"{cluster.key}-{n}"
            n += 1
        used_keys.add(key)
        key_map.setdefault(cluster.key, key)

        new_clusters.append(
            Cluster(key=key, canonical_title=cluster.canonical_title, members=members)
        )

    for draft_id in sorted(draft_ids - set(keep_in)):
        notes.append(f"{draft_id} missing; added as its own cluster")
        key = draft_id
        used_keys.add(key)
        new_clusters.append(
            Cluster(
                key=key,
                canonical_title=titles.get(draft_id, draft_id),
                members=[Member(draft_id=draft_id, role="primary", parent_draft_id=None)],
            )
        )

    alternatives = []
    for a, b in result.alternatives or []:
        if a in key_map and b in key_map:
            alternatives.append((key_map[a], key_map[b]))

    return ClusterResult(clusters=new_clusters, alternatives=alternatives), notes


def enforce_exactly_once(
    results: list[ClusterResult],
    drafts: list[Draft],
) -> tuple[list[ClusterResult], list[str]]:
    """
    Final check across ALL groups: every draft appears in exactly one cluster.

    Grouping already puts each draft in one group, so this should find nothing.
    It is kept as a safety net and repairs rather than failing.
    """
    combined = ClusterResult(
        clusters=[c for r in results for c in r.clusters],
        alternatives=[a for r in results for a in (r.alternatives or [])],
    )
    draft_ids = {d.draft_id for d in drafts}
    titles = {d.draft_id: d.title for d in drafts}
    errors = check_clustering(combined, draft_ids)
    if not errors:
        return results, []
    repaired, notes = repair_cluster_result(combined, draft_ids, titles)
    return [repaired], notes


def expand_followers(
    results: list[ClusterResult],
    followers: dict[str, list[str]],
) -> list[ClusterResult]:
    """
    Add drafts merged by the near-duplicate pre-merge back into their representative's cluster.
    They take the representative's role ('same' if it is primary or same; the same parent if it
    is a sub-task).
    """
    if not followers:
        return results
    for result in results:
        for cluster in result.clusters:
            extra = []
            for m in cluster.members:
                for fid in followers.get(m.draft_id, []):
                    if m.role == "sub_task":
                        extra.append(
                            Member(draft_id=fid, role="sub_task", parent_draft_id=m.parent_draft_id)
                        )
                    else:
                        extra.append(Member(draft_id=fid, role="same", parent_draft_id=None))
            cluster.members.extend(extra)
    return results
