"""
Stage 4a: Blocking — near-duplicate pre-merge and policy-family grouping

Two sequential steps before any LLM clustering call:

1. Near-duplicate pre-merge (premerge_near_duplicates)
   Drafts with the same actor, journeys, and window whose titles match at ≥90%
   (token-sort fuzzy ratio) are merged automatically.  Only the "richest"
   representative (most evidence + sub-tasks) goes to clustering; followers are
   re-attached after clustering via expand_followers().

2. Policy-family grouping (group_drafts)
   Each draft is placed in exactly one group keyed by policy family (POLICY_FAMILY
   dict).  Drafts with policy "Other" inherit the dominant family of their source
   page.  Groups larger than max_group_size (default 60) are split by phase to
   stay within a single LLM context window.

Key functions:
- premerge_near_duplicates(drafts, title_threshold)
      Returns (representatives, followers) where followers is a dict mapping
      representative draft_id → list of absorbed draft_ids.
- group_drafts(drafts, max_group_size)
      Returns a list of non-overlapping groups; asserts every draft appears exactly
      once (will raise if grouping logic ever places a draft in two groups).
- is_near_duplicate(a, b, title_threshold)
      Boolean: True if the two drafts are clearly the same citizen task.
- find_near_duplicates(drafts)
      Union-find algorithm returning sets of size ≥ 2.
- choose_representative(drafts)
      Picks the richest draft from a near-duplicate set.

No file I/O or LLM calls; operates on Draft objects in memory.
"""

from __future__ import annotations

import re
from collections import Counter, defaultdict

from rapidfuzz import fuzz

from src.task_inventory.schema import Draft

# Policies whose drafts are compared with each other in one clustering call.
POLICY_FAMILY: dict[str, str] = {
    "Statutory Maternity Pay": "maternity",
    "Maternity Leave": "maternity",
    "Maternity Allowance": "maternity",
    "Antenatal Rights": "maternity",
    "Paternity Leave and Pay": "partner_and_shared_leave",
    "Shared Parental Leave and Pay": "partner_and_shared_leave",
    "Parental Leave": "partner_and_shared_leave",
    "Neonatal Care Leave and Pay": "neonatal",
    "Bereaved Partner's Paternity Leave": "loss",
    "Stillbirth Registration": "loss",
    "Baby Loss Certificate": "loss",
    "Birth Registration": "registration",
    "Certificates": "registration",
    "Child Benefit": "benefits",
    "Sure Start Maternity Grant": "benefits",
    "Healthy Start": "benefits",
    "Universal Credit": "benefits",
    "Childcare": "benefits",
    "Employment Rights": "employment",
    "Flexible Working": "employment",
}
OTHER_FAMILY = "other"

_STOPWORDS = {
    "a",
    "an",
    "the",
    "your",
    "you",
    "to",
    "for",
    "of",
    "if",
    "and",
    "or",
    "about",
    "with",
}


def policy_family(policy: str) -> str:
    return POLICY_FAMILY.get(policy, OTHER_FAMILY)


def _page_families(drafts: list[Draft]) -> dict[str, str]:
    """Most common family among a page's non-Other drafts."""
    counts: dict[str, Counter] = defaultdict(Counter)
    for d in drafts:
        fam = policy_family(d.policy)
        if fam != OTHER_FAMILY:
            counts[d.source.base_path][fam] += 1
    return {page: c.most_common(1)[0][0] for page, c in counts.items()}


def draft_family(draft: Draft, page_families: dict[str, str]) -> str:
    fam = policy_family(draft.policy)
    if fam == OTHER_FAMILY:
        return page_families.get(draft.source.base_path, OTHER_FAMILY)
    return fam


# ---------------------------------------------------------------------------
# Near-duplicate pre-merge
# ---------------------------------------------------------------------------


def normalise_title(title: str) -> str:
    words = re.sub(r"[^\w\s]", " ", title.lower()).split()
    return " ".join(w for w in words if w not in _STOPWORDS)


def _end_key(end) -> tuple | None:
    return (end.anchor, end.offset, end.unit) if end else None


def window_signature(draft: Draft) -> tuple:
    w = draft.window
    return (_end_key(w.opens) if w else None, _end_key(w.closes) if w else None)


def is_near_duplicate(a: Draft, b: Draft, title_threshold: int = 90) -> bool:
    """Clearly the same task: only then is it safe to merge without the LLM."""
    if a.actor != b.actor:
        return False
    if set(a.journeys) != set(b.journeys):
        return False
    if window_signature(a) != window_signature(b):
        return False
    return (
        fuzz.token_sort_ratio(normalise_title(a.title), normalise_title(b.title)) >= title_threshold
    )


def find_near_duplicates(drafts: list[Draft], title_threshold: int = 90) -> list[list[Draft]]:
    """
    Sets of near-duplicate drafts (size >= 2), across all pages and policies.

    Uses union-find, so A~B and B~C puts A, B, C in one set.
    """
    parent = list(range(len(drafts)))

    def find(i: int) -> int:
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i

    for i in range(len(drafts)):
        for j in range(i + 1, len(drafts)):
            if is_near_duplicate(drafts[i], drafts[j], title_threshold):
                parent[find(j)] = find(i)

    sets: dict[int, list[Draft]] = defaultdict(list)
    for i, d in enumerate(drafts):
        sets[find(i)].append(d)
    return [s for s in sets.values() if len(s) > 1]


def choose_representative(drafts: list[Draft]) -> Draft:
    """The richest draft represents the set (ties broken by draft_id for stability)."""

    def richness(d: Draft) -> tuple:
        n = (
            len(d.evidence)
            + len(d.sub_tasks)
            + len(d.requires)
            + len(d.guidance)
            + len(d.expectations)
        )
        return (-n, d.draft_id)

    return sorted(drafts, key=richness)[0]


def premerge_near_duplicates(
    drafts: list[Draft], title_threshold: int = 90
) -> tuple[list[Draft], dict[str, list[str]]]:
    """
    Returns:
        representatives: drafts to send to grouping/clustering (one per near-duplicate set,
                         plus every draft that has no near-duplicate)
        followers: representative draft_id -> draft_ids merged into it
    """
    followers: dict[str, list[str]] = {}
    hidden: set[str] = set()
    for dup_set in find_near_duplicates(drafts, title_threshold):
        rep = choose_representative(dup_set)
        others = sorted(d.draft_id for d in dup_set if d.draft_id != rep.draft_id)
        followers[rep.draft_id] = others
        hidden.update(others)
    representatives = [d for d in drafts if d.draft_id not in hidden]
    return representatives, followers


# ---------------------------------------------------------------------------
# Grouping
# ---------------------------------------------------------------------------


def group_drafts(drafts: list[Draft], max_group_size: int = 60, **_ignored) -> list[list[Draft]]:
    """
    Group drafts for clustering. Each draft appears in exactly one group.

    1. Group by policy family ("Other" drafts use their page's family)
    2. If a group has more than max_group_size drafts, split it by phase
    """
    page_families = _page_families(drafts)

    by_family: dict[str, list[Draft]] = defaultdict(list)
    for d in drafts:
        by_family[draft_family(d, page_families)].append(d)

    groups: list[list[Draft]] = []
    for family in sorted(by_family):
        members = by_family[family]
        if len(members) <= max_group_size:
            groups.append(members)
            continue
        by_phase: dict[str, list[Draft]] = defaultdict(list)
        for d in members:
            by_phase[d.phase].append(d)
        groups.extend(by_phase[p] for p in sorted(by_phase))

    # Safety net: the grouping must be a partition of the input
    ids = [d.draft_id for g in groups for d in g]
    assert len(ids) == len(set(ids)) == len(drafts), (
        "group_drafts must place every draft exactly once"
    )
    return groups
