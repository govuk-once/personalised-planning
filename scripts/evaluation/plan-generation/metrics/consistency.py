"""Consistency metric: compare G independently generated plans for the same profile.

Computed from the plans with no judge (see ``services.py`` and ``aggregate.py``):
- service stability: pairwise Jaccard overlap of the services each plan recommends
- order agreement: whether each pair of plans puts its shared services in the
  same order
- field mismatches: shared services whose cost or department differ

LLM-judged here, once per repeat:
- same plan: consistency means the user gets the same plan every time. The
  judge lists every meaningful difference between each pair of plans, with a
  severity label (``consistency_prompt.md``); a pair is the same plan when it
  lists none. Plans are then grouped into sets of the same plan, and the
  headline ``modal_plan_share`` is the share of plans in the largest set: how
  often the user gets the most common plan. Each pair is shown in a random but
  repeatable order, so position bias averages out over repeats.
- fact consistency: for each service in two or more plans, the judge checks
  whether the plans' free-text facts about it contradict each other
  (``fact_consistency_prompt.md``). A service is consistent if the judge finds
  no contradiction and its cost and department match.

Requires G >= 2; returns null scores with a note when G < 2.
"""

import itertools
import json
import pathlib
import random
from typing import Any

from metrics.services import field_mismatches, shared_services

_METRICS_DIR = pathlib.Path(__file__).resolve().parent
CONSISTENCY_PROMPT_PATH = _METRICS_DIR / "consistency_prompt.md"
FACT_CONSISTENCY_PROMPT_PATH = _METRICS_DIR / "fact_consistency_prompt.md"

# Difference labels the pair judge may give, least to most severe. They are
# labels for diagnosis, not scores: any difference makes two plans different.
SEVERITIES = (
    "peripheral_step",
    "order",
    "core_step",
    "contradiction",
    "different_approach",
)

# Task fields shown to the judges; the plan's ``reasoning``, task status and
# completion flags are left out. The fact judge does not see cost and dept,
# which ``field_mismatches`` compares without a judge.
_PLAN_TASK_FIELDS = (
    "title",
    "summary",
    "gov_service_name",
    "gov_service_url",
    "dept",
    "cost",
    "deadline",
    "methods",
    "requirements",
    "what_to_expect",
    "callout",
    "grant",
    "location",
    "service_form_label",
)
_FACT_TASK_FIELDS = tuple(f for f in _PLAN_TASK_FIELDS if f not in ("cost", "dept"))


def _pick(task: dict, fields: tuple[str, ...]) -> dict:
    """The given fields of a task, leaving out empty ones."""
    return {f: task[f] for f in fields if task.get(f) not in (None, "", [])}


def _encode_plan(generation: dict) -> str:
    """Encode one plan as JSON for the pairwise judge."""
    plan = generation.get("plan") or {}
    return json.dumps(
        {
            "summary": plan.get("summary", ""),
            "steps": [
                {
                    "title": step.get("title", ""),
                    "summary": step.get("summary", ""),
                    "tasks": [
                        _pick(t, _PLAN_TASK_FIELDS) for t in step.get("tasks") or []
                    ],
                }
                for step in plan.get("steps") or []
            ],
        },
        indent=2,
        ensure_ascii=False,
    )


def _parse_json_object(text: str) -> dict | None:
    """Parse the first JSON object in a judge reply, tolerating code fences."""
    start, end = text.find("{"), text.rfind("}")
    if start == -1 or end < start:
        return None
    try:
        parsed = json.loads(text[start : end + 1])
    except json.JSONDecodeError:
        return None
    return parsed if isinstance(parsed, dict) else None


def _judge_pair(
    judge: Any,
    template: str,
    situation: str,
    context: dict,
    generations: list[dict],
    i: int,
    j: int,
    repeat: int,
) -> dict:
    """Judge one pair of plans (0-based indices ``i`` < ``j``).

    Returns:
        Dict with 1-based ``plans``, ``shown_first``, ``same_plan`` (True if
        the judge lists no differences), ``worst_difference`` (the most severe
        label, or ``"none"``), ``differences`` and ``status`` (``"judged"`` or
        ``"unjudged"``).
    """
    # Seeded per repeat and pair, so a rerun shows the same order.
    swapped = random.Random(f"{repeat}:{i}:{j}").random() < 0.5
    first, second = (j, i) if swapped else (i, j)
    result = {"plans": [i + 1, j + 1], "shown_first": first + 1}
    prompt = template.format(
        situation=situation,
        context=json.dumps(context, sort_keys=True),
        plan_a=_encode_plan(generations[first]),
        plan_b=_encode_plan(generations[second]),
    )
    try:
        parsed = _parse_json_object(judge.generate(prompt)) or {}
    except Exception as exc:  # noqa: BLE001
        return {
            **result,
            "same_plan": None,
            "worst_difference": None,
            "differences": [],
            "status": "unjudged",
            "error": f"judge call failed: {exc}",
        }
    differences = parsed.get("differences")
    if not isinstance(differences, list) or not all(
        isinstance(d, dict) and d.get("severity") in SEVERITIES for d in differences
    ):
        return {
            **result,
            "same_plan": None,
            "worst_difference": None,
            "differences": [],
            "status": "unjudged",
            "error": "could not parse judge output",
        }
    worst = max(
        (d["severity"] for d in differences), key=SEVERITIES.index, default="none"
    )
    return {
        **result,
        "same_plan": not differences,
        "worst_difference": worst,
        "differences": differences,
        "status": "judged",
    }


def _group_same_plans(n_plans: int, pairs: list[dict]) -> list[list[int]] | None:
    """Group plans into sets of the same plan, using the pair verdicts.

    Each plan, in plan order, joins the first set whose first plan it was judged
    the same as, or starts a new set. The judge's verdicts need not be
    transitive, so comparing against one plan per set keeps the sets well defined.

    Args:
        n_plans: Number of plans.
        pairs: Results from ``_judge_pair``, one per pair of plans.

    Returns:
        Lists of 1-based plan numbers, largest set first, or None if a verdict
        the grouping needs is unjudged.
    """
    same = {tuple(p["plans"]): p["same_plan"] for p in pairs}
    groups: list[list[int]] = []
    for plan in range(1, n_plans + 1):
        for group in groups:
            verdict = same.get((group[0], plan))
            if verdict is None:
                return None
            if verdict:
                group.append(plan)
                break
        else:
            groups.append([plan])
    return sorted(groups, key=len, reverse=True)


def _judge_service_facts(judge: Any, template: str, service: dict) -> dict:
    """Judge whether the plans' facts about one shared service contradict.

    Returns:
        Dict with the service's ``name``, ``url``, 1-based ``plans``,
        ``rationale``, ``contradictions`` and ``status``.
    """
    result = {
        "name": service["name"],
        "url": service["url"],
        "plans": sorted(service["tasks"]),
    }
    versions = "\n\n".join(
        f"Plan {plan_no}:\n"
        + json.dumps(_pick(task, _FACT_TASK_FIELDS), indent=2, ensure_ascii=False)
        for plan_no, task in sorted(service["tasks"].items())
    )
    prompt = template.format(
        service=f"{service['name']} ({service['url']})", versions=versions
    )
    try:
        parsed = _parse_json_object(judge.generate(prompt)) or {}
    except Exception as exc:  # noqa: BLE001
        return {
            **result,
            "rationale": "",
            "contradictions": [],
            "status": "unjudged",
            "error": f"judge call failed: {exc}",
        }
    contradictions = parsed.get("contradictions")
    if not isinstance(contradictions, list) or not all(
        isinstance(c, dict) and isinstance(c.get("plans"), list) for c in contradictions
    ):
        return {
            **result,
            "rationale": "",
            "contradictions": [],
            "status": "unjudged",
            "error": "could not parse judge output",
        }
    return {
        **result,
        "rationale": parsed.get("rationale", ""),
        "contradictions": contradictions,
        "status": "judged",
    }


def score_consistency(
    generations: list[dict],
    judge: Any,
    situation: str,
    context: dict,
    repeat: int,
) -> dict:
    """Run the consistency judges once over a profile's G plans.

    Args:
        generations: List of generation dicts, each with a ``plan`` key.
        judge: A ``BedrockJudge``; only its ``generate(prompt)`` is used.
        situation: The profile's situation sentence.
        context: The profile's context dict, as given to the planner.
        repeat: 0-based repeat number; seeds the order each pair is shown in.

    Returns:
        Dict with ``modal_plan_share`` (share of plans in the largest set of
        the same plan, or None), ``same_plan_groups``, ``same_plan_pair_share``
        (share of judged pairs that are the same plan, or None), ``pairs``,
        ``fact_consistency`` (share of shared services with consistent facts,
        or None if no service is shared), ``fact_checks``, ``status``
        (``"judged"`` or ``"skipped"``) and ``note``.
    """
    if len(generations) < 2:
        return {
            "modal_plan_share": None,
            "same_plan_groups": None,
            "same_plan_pair_share": None,
            "pairs": [],
            "fact_consistency": None,
            "fact_checks": [],
            "status": "skipped",
            "note": f"consistency requires G>=2; only {len(generations)} plan(s) generated",
        }

    pair_template = CONSISTENCY_PROMPT_PATH.read_text()
    pairs = [
        _judge_pair(judge, pair_template, situation, context, generations, i, j, repeat)
        for i, j in itertools.combinations(range(len(generations)), 2)
    ]
    verdicts = [p["same_plan"] for p in pairs if p["same_plan"] is not None]
    groups = _group_same_plans(len(generations), pairs)

    fact_template = FACT_CONSISTENCY_PROMPT_PATH.read_text()
    fact_checks = [
        _judge_service_facts(judge, fact_template, service)
        for service in shared_services(generations)
    ]
    mismatched = {(m["url"], m["name"]) for m in field_mismatches(generations)}
    judged_checks = [c for c in fact_checks if c["status"] == "judged"]
    consistent = [
        c
        for c in judged_checks
        if not c["contradictions"] and (c["url"], c["name"]) not in mismatched
    ]

    return {
        "modal_plan_share": len(groups[0]) / len(generations) if groups else None,
        "same_plan_groups": groups,
        "same_plan_pair_share": (sum(verdicts) / len(verdicts) if verdicts else None),
        "pairs": pairs,
        "fact_consistency": (
            len(consistent) / len(judged_checks) if judged_checks else None
        ),
        "fact_checks": fact_checks,
        "status": "judged",
        "note": None,
    }
