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


def _service_tasks(generation: dict) -> dict[str, tuple[int, dict]]:
    """First task naming each service, with the index of the step it is in.

    Args:
        generation: A generation dict with a ``plan`` key.

    Returns:
        ``{service_key: (step_index, task)}`` in plan order.
    """
    found: dict[str, tuple[int, dict]] = {}
    for step_index, step in enumerate(
        (generation.get("plan") or {}).get("steps") or []
    ):
        for task in step.get("tasks") or []:
            key = service_key(task)
            if key and key not in found:
                found[key] = (step_index, task)
    return found


def plan_services(generation: dict) -> dict[str, dict]:
    """Distinct services one plan recommends, in plan order.

    Args:
        generation: A generation dict with a ``plan`` key.

    Returns:
        ``{service_key: {"name", "url"}}``; the first task naming a service wins.
    """
    return {
        key: {
            "name": task.get("gov_service_name") or "",
            "url": task.get("gov_service_url") or "",
        }
        for key, (_, task) in _service_tasks(generation).items()
    }


def pairwise_service_overlaps(generations: list[dict]) -> list[float]:
    """Jaccard overlap of the service sets of every pair of plans.

    Two plans that recommend no services count as identical.

    Args:
        generations: Generation dicts, each with a ``plan`` key.

    Returns:
        One float in [0, 1] per pair of plans; empty with fewer than two plans.
    """
    sets = [set(plan_services(g)) for g in generations]
    return [
        len(a & b) / len(a | b) if (a | b) else 1.0
        for a, b in itertools.combinations(sets, 2)
    ]


def service_stability(generations: list[dict]) -> float | None:
    """Mean pairwise Jaccard overlap of the plans' service sets.

    Averaging over pairs, rather than comparing all plans at once, keeps the
    score from falling just because more plans were generated.

    Args:
        generations: Generation dicts, each with a ``plan`` key.

    Returns:
        A float in [0, 1], or None with fewer than two plans.
    """
    overlaps = pairwise_service_overlaps(generations)
    return statistics.mean(overlaps) if overlaps else None


def _sign(x: int) -> int:
    return (x > 0) - (x < 0)


def pairwise_order_agreement(generations: list[dict]) -> list[float | None]:
    """How far every pair of plans agrees on the order of their shared services.

    For each pair of services both plans recommend, the plans agree if they put
    the two in the same order, or both put them in the same step. Services only
    one plan has are ignored; ``pairwise_service_overlaps`` covers those.

    Args:
        generations: Generation dicts, each with a ``plan`` key.

    Returns:
        One value per pair of plans: the share of shared-service pairs in the
        same order, or None if the plans share fewer than two services.
    """
    positions = [
        {key: step for key, (step, _) in _service_tasks(g).items()} for g in generations
    ]
    agreement: list[float | None] = []
    for a, b in itertools.combinations(positions, 2):
        shared = [key for key in a if key in b]
        service_pairs = list(itertools.combinations(shared, 2))
        if not service_pairs:
            agreement.append(None)
            continue
        same = sum(_sign(a[x] - a[y]) == _sign(b[x] - b[y]) for x, y in service_pairs)
        agreement.append(same / len(service_pairs))
    return agreement


def shared_services(generations: list[dict]) -> list[dict]:
    """Services recommended by two or more plans, with each plan's task for it.

    Args:
        generations: Generation dicts, each with a ``plan`` key.

    Returns:
        List of ``{"key", "name", "url", "tasks"}`` in first-seen order, where
        ``tasks`` maps 1-based plan number to that plan's task for the service.
    """
    by_key: dict[str, dict] = {}
    for plan_no, generation in enumerate(generations, 1):
        for key, (_, task) in _service_tasks(generation).items():
            entry = by_key.setdefault(
                key,
                {
                    "key": key,
                    "name": task.get("gov_service_name") or "",
                    "url": task.get("gov_service_url") or "",
                    "tasks": {},
                },
            )
            entry["tasks"][plan_no] = task
    return [entry for entry in by_key.values() if len(entry["tasks"]) >= 2]


# Structured task fields compared without a judge. Free-text facts go to the
# fact-consistency judge in consistency.py instead.
_COMPARED_FIELDS = ("cost", "dept")


def field_mismatches(generations: list[dict]) -> list[dict]:
    """Shared services whose structured fields differ between plans.

    A plan that leaves a field empty is not counted as disagreeing.

    Args:
        generations: Generation dicts, each with a ``plan`` key.

    Returns:
        One ``{"key", "name", "url", "field", "values"}`` per mismatching field,
        where ``values`` lists ``{"plan", "value"}`` with 1-based plan numbers.
    """
    mismatches = []
    for service in shared_services(generations):
        for field in _COMPARED_FIELDS:
            values = [
                {"plan": plan_no, "value": task.get(field)}
                for plan_no, task in service["tasks"].items()
                if task.get(field) not in (None, "")
            ]
            distinct = {
                v["value"].strip().lower()
                if isinstance(v["value"], str)
                else v["value"]
                for v in values
            }
            if len(distinct) > 1:
                mismatches.append(
                    {
                        "key": service["key"],
                        "name": service["name"],
                        "url": service["url"],
                        "field": field,
                        "values": values,
                    }
                )
    return mismatches
