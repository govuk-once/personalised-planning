"""
Stage 4c: Merging

Deterministic merge of all drafts in one cluster into a single TaskRecord.
No LLM calls — all decisions are rule-based.

Merge rules:
- actor / phase / method  Consensus (all agree → use it; conflict → use primary,
                          flag status=needs_review).
- url                     Most common non-null URL across all members.
- window / duration       All members must agree on (anchor, offset, unit); if they
                          don't, the field is omitted and a conflict is recorded.
- requires / guidance     Fuzzy-deduped union (≥90% text similarity → merge evidence).
- expectations            Grouped by party, then fuzzy-deduped within each party.
- sub_tasks               Primary's sub-tasks first, then 'same' members' (deduped),
                          then sub_task members converted to sub-tasks.
- journeys                Union of all members' journey lists.
- evidence                Union of all cited sentence IDs.

A nothing-lost assertion verifies that every window, duration, and evidence ID
from every member appears in the merged TaskRecord.

Key functions:
- merge_cluster(cluster, drafts_by_id, existing_ids)
      Top-level entry point; returns (TaskRecord, conflicts).
- make_task_id(policy, canonical_title, existing_ids)
      slug(policy)--slug(canonical_title), with numeric suffix on collision.
- merge_windows(drafts) / merge_durations(drafts)
      Returns (merged_value | None, conflict_strings).
- merge_cited_list(items, similarity_threshold)
      Fuzzy-dedup a list of Cited objects, combining evidence of near-identical text.

No file I/O; operates on in-memory objects.
"""

import re
from collections import Counter

from rapidfuzz import fuzz

from src.task_inventory.schema import (
    Cited,
    Cluster,
    Draft,
    Duration,
    Expectation,
    SubTask,
    TaskRecord,
    Window,
    WindowEnd,
)


def slug(text: str) -> str:
    """Convert text to kebab-case slug"""
    # Remove special chars, convert to lowercase
    text = re.sub(r"[^\w\s-]", "", text.lower())
    # Replace whitespace with hyphens
    text = re.sub(r"[\s_]+", "-", text)
    # Remove duplicate hyphens
    text = re.sub(r"-+", "-", text)
    return text.strip("-")


def make_task_id(policy: str, canonical_title: str, existing_ids: set[str]) -> str:
    """
    Create task ID: slug(policy)--slug(canonical_title)

    Add numeric suffix if collision.
    """
    policy_slug = slug(policy)
    title_slug = slug(canonical_title)
    base_id = f"{policy_slug}--{title_slug}"

    if base_id not in existing_ids:
        return base_id

    # Handle collision
    n = 2
    while f"{base_id}-{n}" in existing_ids:
        n += 1
    return f"{base_id}-{n}"


def merge_field_by_consensus(values: list[str], primary_value: str) -> tuple[str, bool]:
    """
    Merge a simple field (actor, phase, method).

    Returns: (chosen_value, is_conflict)
    """
    unique_values = list(set(values))

    if len(unique_values) == 1:
        # All agree
        return unique_values[0], False
    else:
        # Conflict: use primary's value provisionally
        return primary_value, True


def merge_cited_list(items: list[Cited], similarity_threshold: int = 90) -> list[Cited]:
    """
    Merge list of Cited items (requires, expectations, guidance).

    Combines items with similar text (≥90% similarity), keeping all evidence.
    """
    if not items:
        return []

    merged = []
    used = set()

    for i, item in enumerate(items):
        if i in used:
            continue

        # Find similar items
        similar_indices = [i]
        for j, other in enumerate(items[i + 1 :], start=i + 1):
            if j in used:
                continue

            similarity = fuzz.ratio(item.text, other.text)
            if similarity >= similarity_threshold:
                similar_indices.append(j)
                used.add(j)

        # Merge evidence
        all_evidence = []
        for idx in similar_indices:
            all_evidence.extend(items[idx].evidence)

        merged_item = Cited(
            text=item.text,  # Use first item's text
            evidence=sorted(set(all_evidence)),
        )
        merged.append(merged_item)
        used.add(i)

    return merged


def merge_sub_tasks(
    primary: Draft, members: list[Draft], similarity_threshold: int = 90
) -> list[SubTask]:
    """
    Merge sub-tasks from all members.

    Primary's sub-tasks first, then same members' (merged if similar), then sub_task members.
    """
    result = []

    # Start with primary's sub-tasks
    result.extend(primary.sub_tasks)

    # Add sub-tasks from 'same' members
    for member in members:
        for sub in member.sub_tasks:
            # Check if similar to existing
            similar = False
            for i, existing in enumerate(result):
                if (
                    existing.window
                    and sub.window
                    and _window_sig(existing.window) != _window_sig(sub.window)
                ):
                    continue  # different deadlines: keep both sub-tasks
                similarity = fuzz.ratio(sub.text, existing.text)
                if similarity >= similarity_threshold:
                    # Merge evidence
                    combined_evidence = sorted(set(existing.evidence + sub.evidence))
                    # Keep existing text, add evidence
                    result[i] = SubTask(
                        text=existing.text,
                        evidence=combined_evidence,
                        window=existing.window or sub.window,  # Prefer first non-null window
                    )
                    similar = True
                    break

            if not similar:
                result.append(sub)

    # Sub_task members will be added separately in merge_cluster

    return result


def _window_sig(window: Window | None) -> tuple:
    if not window:
        return (None, None)
    return (window_key(window.opens), window_key(window.closes))


def window_key(window_end: WindowEnd | None) -> tuple | None:
    """Create hashable key for a window end"""
    if not window_end:
        return None
    return (window_end.anchor, window_end.offset, window_end.unit)


def merge_windows(drafts: list[Draft]) -> tuple[Window | None, list[str]]:
    """
    Merge window fields from multiple drafts.

    Returns: (merged_window, list_of_conflicts)

    If all drafts agree on (anchor, offset, unit), combine evidence.
    If they disagree, it's a blocking conflict.
    """
    opens_variants = []
    closes_variants = []

    for draft in drafts:
        if not draft.window:
            continue

        if draft.window.opens:
            opens_variants.append(draft.window.opens)

        if draft.window.closes:
            closes_variants.append(draft.window.closes)

    conflicts = []
    merged_window = Window()

    # Merge opens
    if opens_variants:
        keys = [window_key(w) for w in opens_variants]
        unique_keys = {k for k in keys if k}

        if len(unique_keys) == 1:
            # All agree
            all_evidence = []
            for w in opens_variants:
                all_evidence.extend(w.evidence)

            first = opens_variants[0]
            merged_window.opens = WindowEnd(
                anchor=first.anchor,
                offset=first.offset,
                unit=first.unit,
                evidence=sorted(set(all_evidence)),
            )
        else:
            # Conflict
            variants_str = ", ".join(str(k) for k in unique_keys)
            conflicts.append(f"window.opens: {variants_str}")

    # Merge closes
    if closes_variants:
        keys = [window_key(w) for w in closes_variants]
        unique_keys = {k for k in keys if k}

        if len(unique_keys) == 1:
            # All agree
            all_evidence = []
            for w in closes_variants:
                all_evidence.extend(w.evidence)

            first = closes_variants[0]
            merged_window.closes = WindowEnd(
                anchor=first.anchor,
                offset=first.offset,
                unit=first.unit,
                evidence=sorted(set(all_evidence)),
            )
        else:
            # Conflict
            variants_str = ", ".join(str(k) for k in unique_keys)
            conflicts.append(f"window.closes: {variants_str}")

    if not merged_window.opens and not merged_window.closes:
        merged_window = None

    return merged_window, conflicts


def merge_durations(drafts: list[Draft]) -> tuple[Duration | None, list[str]]:
    """Merge duration fields (same logic as windows)"""
    durations = [d.duration for d in drafts if d.duration]

    if not durations:
        return None, []

    # Check if all agree on (value, unit)
    keys = {(d.value, d.unit) for d in durations}

    if len(keys) == 1:
        # All agree
        all_evidence = []
        for d in durations:
            all_evidence.extend(d.evidence)

        first = durations[0]
        return Duration(value=first.value, unit=first.unit, evidence=sorted(set(all_evidence))), []
    else:
        # Conflict
        variants_str = ", ".join(f"{v}{u}" for v, u in keys)
        return None, [f"duration: {variants_str}"]


def merge_cluster(
    cluster: Cluster, drafts_by_id: dict[str, Draft], existing_ids: set[str]
) -> tuple[TaskRecord, list[str]]:
    """
    Merge one cluster into a TaskRecord.

    Args:
        cluster: Cluster with members
        drafts_by_id: Lookup from draft_id to Draft
        existing_ids: Set of task IDs already used (for collision detection)

    Returns:
        (TaskRecord, list_of_conflicts)

    Raises:
        AssertionError: If nothing-lost check fails
    """
    # Get drafts
    primary_member = next(m for m in cluster.members if m.role == "primary")
    primary = drafts_by_id[primary_member.draft_id]

    same_members = [drafts_by_id[m.draft_id] for m in cluster.members if m.role == "same"]

    sub_task_members = [drafts_by_id[m.draft_id] for m in cluster.members if m.role == "sub_task"]

    all_members = [primary] + same_members + sub_task_members

    # Create task ID
    task_id = make_task_id(primary.policy, cluster.canonical_title, existing_ids)

    conflicts = []

    # Simple fields: use consensus or primary
    actors = [d.actor for d in [primary] + same_members]
    actor, actor_conflict = merge_field_by_consensus(actors, primary.actor)
    if actor_conflict:
        conflicts.append(f"actor: {set(actors)}")

    phases = [d.phase for d in [primary] + same_members]
    phase, phase_conflict = merge_field_by_consensus(phases, primary.phase)
    if phase_conflict:
        conflicts.append(f"phase: {set(phases)}")

    methods = [d.method for d in [primary] + same_members]
    method, method_conflict = merge_field_by_consensus(methods, primary.method)
    if method_conflict:
        conflicts.append(f"method: {set(methods)}")

    # URL: primary's, or most common
    urls = [d.url for d in all_members if d.url]
    if urls:
        url_counts = Counter(urls)
        url = url_counts.most_common(1)[0][0]
    else:
        url = None

    # Window and duration (with conflict detection)
    window, window_conflicts = merge_windows([primary] + same_members)
    conflicts.extend(window_conflicts)

    duration, duration_conflicts = merge_durations([primary] + same_members)
    conflicts.extend(duration_conflicts)

    # Cited lists
    all_requires = []
    all_expectations = []
    all_guidance = []

    # Includes sub_task members: their requires and expectations move to the parent task
    for draft in all_members:
        all_requires.extend(draft.requires)
        all_expectations.extend(draft.expectations)
        all_guidance.extend(draft.guidance)

    requires = merge_cited_list(all_requires)
    guidance = merge_cited_list(all_guidance)

    # Expectations need special handling (they have party field)
    expectations = []
    if all_expectations:
        # Group by party, then merge within each party
        by_party = {}
        for exp in all_expectations:
            if exp.party not in by_party:
                by_party[exp.party] = []
            by_party[exp.party].append(Cited(text=exp.text, evidence=exp.evidence))

        for party, cited_list in by_party.items():
            merged_cited = merge_cited_list(cited_list)
            for cited in merged_cited:
                expectations.append(
                    Expectation(party=party, text=cited.text, evidence=cited.evidence)
                )

    # Sub-tasks
    sub_tasks = merge_sub_tasks(primary, same_members)

    # Add sub_task members as new sub-tasks
    for member in cluster.members:
        if member.role == "sub_task":
            sub_draft = drafts_by_id[member.draft_id]
            # Add as sub-task (its requires and expectations were already merged into the parent above)
            sub_tasks.append(
                SubTask(text=sub_draft.title, evidence=sub_draft.evidence, window=sub_draft.window)
            )
            # Keep the sub-task draft's own sub-tasks as further steps
            for inner in sub_draft.sub_tasks:
                sub_tasks.append(inner)

    # Journeys: union
    journeys = sorted({j for d in all_members for j in d.journeys})

    # Check for typical + special conflict
    if "typical" in journeys:
        special = {"neonatal", "loss", "abroad", "surrogacy"}
        if any(j in journeys for j in special):
            conflicts.append(f"journeys: typical appears with {special & set(journeys)}")

    # Evidence: union
    all_evidence = sorted({e for d in all_members for e in d.evidence})

    # Sources
    sources = [d.source for d in all_members]

    # Create TaskRecord
    task = TaskRecord(
        id=task_id,
        policy=primary.policy,
        title=cluster.canonical_title,
        actor=actor,
        method=method,
        url=url,
        window=window,
        duration=duration,
        requires=requires,
        expectations=expectations,
        sub_tasks=sub_tasks,
        guidance=guidance,
        phase=phase,
        journeys=journeys,
        evidence=all_evidence,
        sources=sources,
        sensitivity="normal",  # Will be set by model_validator
        alternative_to=[],  # Filled in later
        variants=[],
        status="needs_review" if conflicts else "ok",
    )

    # Nothing-lost check
    # Collect distinct window/duration values from all members
    member_windows = set()
    member_durations = set()

    def _collect(window, into):
        if window:
            if window.opens:
                into.add(window_key(window.opens))
            if window.closes:
                into.add(window_key(window.closes))

    for draft in [primary] + same_members:
        _collect(draft.window, member_windows)
        if draft.duration:
            member_durations.add((draft.duration.value, draft.duration.unit))

    # Windows from sub_task members, and from every member's own sub-tasks,
    # must survive as sub-task windows
    member_sub_windows = set()
    for draft in all_members:
        for sub in draft.sub_tasks:
            _collect(sub.window, member_sub_windows)
    for draft in sub_task_members:
        _collect(draft.window, member_sub_windows)

    task_windows = set()
    _collect(task.window, task_windows)
    task_sub_windows = set()
    for sub in task.sub_tasks:
        _collect(sub.window, task_sub_windows)

    missing_sub_windows = member_sub_windows - task_sub_windows
    if missing_sub_windows:
        raise AssertionError(
            f"Nothing-lost check failed for {task_id}: sub-task windows {missing_sub_windows} not in merged task"
        )

    task_durations = set()
    if task.duration:
        task_durations.add((task.duration.value, task.duration.unit))

    # If there are conflicting windows, we expect them NOT to all be in the merged task
    # So only check if no conflicts
    if not window_conflicts:
        missing_windows = member_windows - task_windows
        if missing_windows:
            raise AssertionError(
                f"Nothing-lost check failed for {task_id}: windows {missing_windows} from members not in merged task"
            )

    if not duration_conflicts:
        missing_durations = member_durations - task_durations
        if missing_durations:
            raise AssertionError(
                f"Nothing-lost check failed for {task_id}: durations {missing_durations} from members not in merged task"
            )

    # Check all member evidence is in task evidence
    task_evidence_set = set(task.evidence)
    for draft in all_members:
        missing_evidence = set(draft.evidence) - task_evidence_set
        if missing_evidence:
            raise AssertionError(
                f"Nothing-lost check failed for {task_id}: evidence {missing_evidence} from {draft.draft_id} not in merged task"
            )

    return task, conflicts
