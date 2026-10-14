"""Which gov.uk services a plan recommends, and how stable that set is across plans.

Kept free of heavy imports so a relevance-only run never loads deepeval.
"""

import itertools
import statistics


def service_key(task: dict) -> str | None:
    """Identify the service a task points at.

    Uses the normalised ``gov_service_url`` (same normalisation as
    ``run_app.url_index``) so URL spelling variants collapse to one service, and
    falls back to the service name when there is no usable URL.

    Args:
        task: A task dict from a plan.

    Returns:
        A stable key, or None if the task names no service.
    """
    raw = task.get("gov_service_url") or ""
    path = raw.split("?")[0].split("#")[0].rstrip("/")
    path = path.replace("https://www.gov.uk", "").replace("http://www.gov.uk", "")
    if path:
        return f"url:{path.lower()}"
    name = (task.get("gov_service_name") or "").strip().lower()
    return f"name:{name}" if name else None


def plan_services(generation: dict) -> dict[str, dict]:
    """Distinct services one plan recommends, in plan order.

    Args:
        generation: A generation dict with a ``plan`` key.

    Returns:
        ``{service_key: {"name", "url"}}``; the first task naming a service wins.
    """
    found: dict[str, dict] = {}
    for step in (generation.get("plan") or {}).get("steps") or []:
        for task in step.get("tasks") or []:
            key = service_key(task)
            if key and key not in found:
                found[key] = {
                    "name": task.get("gov_service_name") or "",
                    "url": task.get("gov_service_url") or "",
                }
    return found


def service_stability(generations: list[dict]) -> float | None:
    """Mean pairwise Jaccard overlap of the plans' service sets.

    Averaging over pairs, rather than comparing all plans at once, keeps the
    score from falling just because more plans were generated. Two plans that
    recommend no services count as identical.

    Args:
        generations: Generation dicts, each with a ``plan`` key.

    Returns:
        A float in [0, 1], or None with fewer than two plans.
    """
    sets = [set(plan_services(g)) for g in generations]
    if len(sets) < 2:
        return None
    overlaps = [
        len(a & b) / len(a | b) if (a | b) else 1.0
        for a, b in itertools.combinations(sets, 2)
    ]
    return statistics.mean(overlaps)
