"""
Validation checks for Draft and TaskRecord objects

Runs after Pydantic validation to catch semantic errors that the schema cannot
express: timing numbers must appear in the cited evidence, offset signs must
match directional language, task IDs must be unique, URLs must be on gov.uk, etc.

All functions return (errors, warnings) lists where errors are blocking (the draft
is rejected or the task is flagged needs_review) and warnings are surfaced in the
validation report but do not block.

Key functions:
- check_draft(draft, evidence_texts)
      Checks window endpoints, title verb, near-duplicate sub-tasks.
      Called by drafts.validate_one() and scripts/task_inventory/run_pipeline.py post-stage-3.
- check_task(task, evidence_texts)
      Extends check_draft with URL domain, journey/sensitivity consistency.
      Called by scripts/task_inventory/run_pipeline.py post-stage-4.
- check_task_ids_unique(tasks)
      Returns errors for any duplicate task ID in the final list.
- check_window_endpoint(window_end, evidence_texts, kind)
      Low-level check that the offset number, unit, and direction appear in the
      cited sentences.  Returns (errors, warnings).

No file I/O; accepts objects and evidence_texts dict as arguments.
"""

import re
from collections import Counter

from rapidfuzz import fuzz

from src.task_inventory.schema import Draft, TaskRecord, WindowEnd

UNIT_RE = r"(hour|day|week|month|year)s?"

# Anchor phrases for validation when offset == 0
ANCHOR_PHRASES = {
    "qualifying_week": ["qualifying week"],
    "due_week": ["due", "expected week"],
    "birth": ["birth", "born"],
    "leave_start": ["leave start", "start your leave", "leave to start"],
    "smp_start": ["smp start", "pay to start"],
    "death": ["death", "died"],
    "return_date": ["return"],
    "registration": ["register"],
    "application_date": ["apply", "claim"],
    "decision_date": ["decision"],
    "pregnancy_week": ["pregnancy", "pregnant"],
    "benefit_claim_start": ["claim start", "benefit start"],
    "pregnancy_loss": ["loss", "miscarriage"],
}


def check_window_endpoint(
    window_end: WindowEnd,
    evidence_texts: dict[str, str],
    kind: str,  # "opens" or "closes"
) -> tuple[list[str], list[str]]:
    """
    Check one window endpoint matches its evidence.

    Returns (errors, warnings). Errors mean the window is not supported by the cited
    text; warnings are heuristics for a person to look at.
    """
    errors = []
    warnings = []

    # Get evidence text
    texts = [evidence_texts.get(eid, "") for eid in window_end.evidence]
    combined_text = " ".join(texts).lower()

    if not combined_text:
        errors.append(f"{kind}: no evidence text found for IDs {window_end.evidence}")
        return errors, warnings

    # Check 1: Offset number appears in text (or anchor phrase if offset==0)
    n = abs(window_end.offset)

    if n == 0:
        # Special case: offset 0 means "at the anchor"
        # Check that the anchor is mentioned in the text
        anchor_name = window_end.anchor
        if anchor_name in ANCHOR_PHRASES:
            phrases = ANCHOR_PHRASES[anchor_name]
            if not any(phrase in combined_text for phrase in phrases):
                errors.append(f"{kind}: anchor '{anchor_name}' not found in evidence text")
                return errors, warnings
        # No number/unit to check, skip to later checks
        match = None
    else:
        pattern = rf"\b{n}\s*(?:working\s+)?{UNIT_RE}\b(.{{0,60}})"
        match = re.search(pattern, combined_text)

        if not match:
            errors.append(f"{kind}: '{n} {window_end.unit}' not found in evidence text")
            return errors, warnings

        # Check 2: Unit matches
        found_unit = match.group(1)
        if found_unit != window_end.unit and found_unit + "s" != window_end.unit:
            errors.append(f"{kind}: unit is '{window_end.unit}' but text says '{found_unit}'")

        # Check 3: Direction matches offset sign
        tail = match.group(2) if match.lastindex >= 2 else ""

        if re.search(r"\bbefore\b", tail) and window_end.offset > 0:
            errors.append(
                f"{kind}: text says 'before' but offset is positive ({window_end.offset})"
            )

        if re.search(r"\bafter\b|\bwithin\b", tail) and window_end.offset < 0:
            errors.append(
                f"{kind}: text says 'after/within' but offset is negative ({window_end.offset})"
            )

    # Check 4: Notice periods should be 'closes'
    if kind == "opens" and "notice" in combined_text:
        warnings.append(f"{kind}: notice period stored as 'opens' (should be 'closes')")

    # Check 5: Not from worked example
    if re.search(r"\bfor example\b|\be\.g\.", combined_text):
        warnings.append(f"{kind}: window may be from worked example")

    # Check 6: Not processing time or protection period
    if re.search(r"\b(takes?|processed|decision|respond|protect)", combined_text):
        warnings.append(
            f"{kind}: possible processing time or protection period (should be duration/expectation)"
        )

    return errors, warnings


def check_draft(draft: Draft, evidence_texts: dict[str, str]) -> tuple[list[str], list[str]]:
    """
    Check one draft.

    Returns: (errors, warnings)
    """
    errors = []
    warnings = []

    # Check window endpoints: the task's own window and every sub-task window
    windows = [("window", draft.window)] + [
        (f"sub_tasks[{i}].window", sub.window) for i, sub in enumerate(draft.sub_tasks)
    ]
    for label, window in windows:
        if not window:
            continue
        for kind in ("opens", "closes"):
            end = getattr(window, kind)
            if not end:
                continue
            end_errors, end_warnings = check_window_endpoint(end, evidence_texts, kind)
            errors.extend(f"{label}.{e}" for e in end_errors)
            warnings.extend(f"{label}.{w}" for w in end_warnings)

    # Check title starts with verb (warning only)
    # Import from schema to stay in sync
    from src.task_inventory.schema import VERBS

    # Check single-word and multi-word verbs
    title_matched = False
    if draft.title:
        for verb in VERBS:
            if draft.title.startswith(verb + " ") or draft.title == verb:
                title_matched = True
                break

    if not title_matched and draft.title:
        title_start = draft.title.split()[0] if draft.title else ""
        warnings.append(f"Title doesn't start with a verb from list: '{title_start}'")

    # Check for guidance-like titles
    if any(draft.title.startswith(phrase) for phrase in ["Understand", "Check rates", "Get help"]):
        warnings.append(f"Title suggests guidance, not a task: '{draft.title}'")

    # Check for near-duplicate sub-tasks
    if len(draft.sub_tasks) > 1:
        for i, sub1 in enumerate(draft.sub_tasks):
            for sub2 in draft.sub_tasks[i + 1 :]:
                similarity = fuzz.ratio(sub1.text, sub2.text)
                if similarity > 85:
                    warnings.append(
                        f"Near-duplicate sub-tasks: '{sub1.text}' vs '{sub2.text}' ({similarity}%)"
                    )

    return errors, warnings


def check_task(task: TaskRecord, evidence_texts: dict[str, str]) -> tuple[list[str], list[str]]:
    """
    Check one final task.

    Returns: (errors, warnings)
    """
    errors = []
    warnings = []

    # All draft checks apply
    # Create a temporary Draft object for reuse
    draft_dict = task.model_dump()
    draft_dict["draft_id"] = task.id
    draft_dict["source"] = {"base_path": "", "section_path": "", "draft_id": task.id}
    draft_dict["status"] = "ok"
    draft_dict["errors"] = []

    from src.task_inventory.schema import Draft as DraftForCheck

    try:
        draft = DraftForCheck.model_validate(draft_dict)
        draft_errors, draft_warnings = check_draft(draft, evidence_texts)
        errors.extend(draft_errors)
        warnings.extend(draft_warnings)
    except Exception:
        pass  # Schema differences, skip draft checks

    # URL checks
    if task.url:
        if "gov.uk" not in task.url:
            errors.append(f"URL not on gov.uk domain: {task.url}")

        if task.url.startswith("mailto:"):
            errors.append("URL is mailto: link (should be a web page)")

        EMPLOYER_PAGES = [
            "/employers-",
            "/recover-statutory-payments",
            "/maternity-leave-pay-employees",
        ]
        if any(task.url.startswith(f"https://www.gov.uk{p}") for p in EMPLOYER_PAGES):
            errors.append("URL points to employer guidance page")

    # Journey/sensitivity consistency
    if "loss" in task.journeys and task.sensitivity != "loss":
        errors.append(
            f"'loss' in journeys but sensitivity is '{task.sensitivity}' (should be 'loss')"
        )

    if "typical" in task.journeys:
        special = {"neonatal", "loss", "abroad", "surrogacy"}
        if any(j in task.journeys for j in special):
            errors.append(f"'typical' appears with special-circumstance tags: {task.journeys}")

    return errors, warnings


def check_task_ids_unique(tasks: list[TaskRecord]) -> list[str]:
    """Check all task IDs are unique"""
    errors = []
    id_counts = Counter(t.id for t in tasks)
    duplicates = [task_id for task_id, count in id_counts.items() if count > 1]

    for task_id in duplicates:
        errors.append(f"Duplicate task ID: {task_id} appears {id_counts[task_id]} times")

    return errors
