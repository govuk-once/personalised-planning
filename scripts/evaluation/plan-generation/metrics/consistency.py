"""Consistency metric: compare G independently generated plans for the same profile.

Three measures, each covering something the others do not:
- task overlap (``service_stability``): do the plans recommend the same
  services? Computed from the plans with no judge (see ``services.py``).
- fact consistency: where plans recommend the same service, do they say the same
  things about it (cost, department, deadline, requirements and so on)? One
  judge call per service in two or more plans (``fact_consistency_prompt.md``).
- structure consistency: do the plans have the same steps, in the same order,
  and the same plan summary? One judge call per pair of plans
  (``structure_consistency_prompt.md``). A pair is consistent when the judge
  lists no differences. Each pair is shown in a random but repeatable order, so
  position bias averages out over repeats.

A judge call that fails or returns an unusable reply is retried (see
``retry.py``); if it still fails, that pair or service is ``"unjudged"`` and
left out of the score. Access denied and missing or expired credentials are not
stepped over: they raise ``FatalJudgeError``.

Requires G >= 2; returns null scores with a note when G < 2.
"""

import itertools
import json
import pathlib
import random
from typing import Any

from metrics.retry import BadReply, FatalJudgeError, with_retries
from metrics.services import shared_services

_METRICS_DIR = pathlib.Path(__file__).resolve().parent
STRUCTURE_PROMPT_PATH = _METRICS_DIR / "structure_consistency_prompt.md"
FACT_PROMPT_PATH = _METRICS_DIR / "fact_consistency_prompt.md"

# Task fields the fact judge compares; the plan's ``reasoning``, task status and
# completion flags are left out.
_FACT_TASK_FIELDS = (
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


def _pick(task: dict, fields: tuple[str, ...]) -> dict:
    """The given fields of a task, leaving out empty ones."""
    return {f: task[f] for f in fields if task.get(f) not in (None, "", [])}


def _encode_structure(generation: dict) -> str:
    """Encode a plan's summary and steps (no tasks) as JSON for the structure judge."""
    plan = generation.get("plan") or {}
    return json.dumps(
        {
            "summary": plan.get("summary", ""),
            "steps": [
                {"title": step.get("title", ""), "summary": step.get("summary", "")}
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
    """Judge the structure of one pair of plans (0-based indices ``i`` < ``j``).

    Returns:
        Dict with 1-based ``plans``, ``shown_first``, ``same`` (True if the
        judge lists no differences), ``differences`` and ``status``
        (``"judged"`` or ``"unjudged"``, with an ``error`` if unjudged).
    """
    # Seeded per repeat and pair, so a rerun shows the same order.
    swapped = random.Random(f"{repeat}:{i}:{j}").random() < 0.5
    first, second = (j, i) if swapped else (i, j)
    result = {"plans": [i + 1, j + 1], "shown_first": first + 1}
    unjudged = {**result, "same": None, "differences": [], "status": "unjudged"}
    prompt = template.format(
        situation=situation,
        context=json.dumps(context, sort_keys=True),
        plan_a=_encode_structure(generations[first]),
        plan_b=_encode_structure(generations[second]),
    )

    def attempt() -> list:
        parsed = _parse_json_object(judge.generate(prompt)) or {}
        differences = parsed.get("differences")
        if not isinstance(differences, list) or not all(
            isinstance(d, dict) and isinstance(d.get("description"), str)
            for d in differences
        ):
            raise BadReply("could not parse judge output")
        return differences

    try:
        differences = with_retries(attempt, f"structure judge, plans {i + 1}-{j + 1}")
    except BadReply as exc:
        return {**unjudged, "error": str(exc)}
    except FatalJudgeError:
        raise
    except Exception as exc:  # noqa: BLE001
        return {**unjudged, "error": f"judge call failed: {exc}"}
    return {
        **result,
        "same": not differences,
        "differences": differences,
        "status": "judged",
    }


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
    unjudged = {**result, "rationale": "", "contradictions": [], "status": "unjudged"}
    versions = "\n\n".join(
        f"Plan {plan_no}:\n"
        + json.dumps(_pick(task, _FACT_TASK_FIELDS), indent=2, ensure_ascii=False)
        for plan_no, task in sorted(service["tasks"].items())
    )
    prompt = template.format(
        service=f"{service['name']} ({service['url']})", versions=versions
    )

    def attempt() -> dict:
        parsed = _parse_json_object(judge.generate(prompt)) or {}
        contradictions = parsed.get("contradictions")
        if not isinstance(contradictions, list) or not all(
            isinstance(c, dict) and isinstance(c.get("plans"), list)
            for c in contradictions
        ):
            raise BadReply("could not parse judge output")
        return parsed

    try:
        parsed = with_retries(attempt, f"fact judge, {service['name']}")
    except BadReply as exc:
        return {**unjudged, "error": str(exc)}
    except FatalJudgeError:
        raise
    except Exception as exc:  # noqa: BLE001
        return {**unjudged, "error": f"judge call failed: {exc}"}
    return {
        **result,
        "rationale": parsed.get("rationale", ""),
        "contradictions": parsed["contradictions"],
        "status": "judged",
    }


def _share(flags: list[bool]) -> float | None:
    """Share of True values, or None if there are none."""
    return sum(flags) / len(flags) if flags else None


def score_consistency(
    generations: list[dict],
    judge: Any,
    situation: str,
    context: dict,
    repeat: int,
) -> dict:
    """Run the two consistency judges once over a profile's G plans.

    Args:
        generations: List of generation dicts, each with a ``plan`` key.
        judge: A ``BedrockJudge``; only its ``generate(prompt)`` is used.
        situation: The profile's situation sentence.
        context: The profile's context dict, as given to the planner.
        repeat: 0-based repeat number; seeds the order each pair is shown in.

    Returns:
        Dict with ``structure_consistency`` (share of judged pairs of plans with
        the same structure, or None), ``pairs``, ``fact_consistency`` (share of
        judged shared services with no contradiction, or None if no service is
        shared), ``fact_checks``, ``status`` (``"judged"`` or ``"skipped"``) and
        ``note``.
    """
    if len(generations) < 2:
        return {
            "structure_consistency": None,
            "pairs": [],
            "fact_consistency": None,
            "fact_checks": [],
            "status": "skipped",
            "note": f"consistency requires G>=2; only {len(generations)} plan(s) generated",
        }

    structure_template = STRUCTURE_PROMPT_PATH.read_text()
    pairs = [
        _judge_pair(
            judge, structure_template, situation, context, generations, i, j, repeat
        )
        for i, j in itertools.combinations(range(len(generations)), 2)
    ]

    fact_template = FACT_PROMPT_PATH.read_text()
    fact_checks = [
        _judge_service_facts(judge, fact_template, service)
        for service in shared_services(generations)
    ]

    return {
        "structure_consistency": _share(
            [p["same"] for p in pairs if p["status"] == "judged"]
        ),
        "pairs": pairs,
        "fact_consistency": _share(
            [not c["contradictions"] for c in fact_checks if c["status"] == "judged"]
        ),
        "fact_checks": fact_checks,
        "status": "judged",
        "note": None,
    }
