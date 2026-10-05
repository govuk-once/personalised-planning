"""Consistency metric: compare G independently generated plans for the same profile.

Two GEval dimensions:
- Service-set stability: are the same gov.uk services recommended across runs?
- Holistic consistency: are the plans substantively the same (strategy, steps,
  advice), ignoring wording/tone differences?

Requires G >= 2; returns null scores with a note when G < 2.
"""

from typing import Any

from deepeval.metrics import GEval
from deepeval.test_case import LLMTestCase, SingleTurnParams


def _encode_plans(generations: list[dict]) -> str:
    """Encode G plans as labelled blocks for a multi-plan judge.

    Args:
        generations: List of generation dicts (each has a ``plan`` key).

    Returns:
        Multi-block string with one ``=== PLAN VERSION n ===`` section per plan.
    """
    parts = []
    for i, gen in enumerate(generations, 1):
        plan = gen.get("plan") or {}
        services = []
        for step in plan.get("steps", []):
            for task in step.get("tasks", []):
                name = task.get("gov_service_name", "")
                url = task.get("gov_service_url", "")
                if name or url:
                    services.append(f"{name} ({url})")
        step_titles = [s.get("title", "") for s in plan.get("steps", [])]
        parts.append(
            f"=== PLAN VERSION {i} ===\n"
            f"Title: {plan.get('title', '')}\n"
            f"Steps ({len(plan.get('steps', []))}): {'; '.join(step_titles)}\n"
            f"Services: {'; '.join(services) or '(none)'}\n"
            f"Summary: {plan.get('summary', '')}"
        )
    return "\n\n".join(parts)


_STABILITY_STEPS = [
    "Extract the complete set of recommended government services (name + URL) from each plan version.",
    "Compare the service sets across all versions, ignoring order.",
    "Score 1.0 if every version recommends an identical set of services. "
    "Reduce the score proportionally for each service that appears in some versions but not others. "
    "Score 0.0 if versions share no services in common.",
]

_HOLISTIC_STEPS = [
    "Read all plan versions and identify the overall planning strategy and the sequence of recommended steps.",
    "Compare the step structure, key advice, and overall approach across all versions.",
    "Score 1.0 if all versions are substantively identical: same steps, same strategy, same key advice, "
    "allowing for minor wording or ordering variation. "
    "Reduce the score for each meaningful structural or strategic difference. "
    "Score 0.0 if versions represent entirely different approaches to the same situation.",
]


def score_consistency(
    generations: list[dict],
    judge_model: Any,
    situation: str,
) -> dict:
    """Score plan consistency across G generations.

    Args:
        generations: List of generation dicts from ``generation.generate_plans``.
        judge_model: A ``BedrockJudge`` (or any ``DeepEvalBaseLLM``) instance.
        situation: The life-event situation string.

    Returns:
        Dict with ``service_stability`` (float|None), ``holistic`` (float|None),
        ``reasons`` (dict), ``status`` (``"judged"`` or ``"skipped"``), and
        optional ``note``.
    """
    if len(generations) < 2:
        return {
            "service_stability": None,
            "holistic": None,
            "reasons": {},
            "status": "skipped",
            "note": f"consistency requires G>=2; only {len(generations)} plan(s) generated",
        }

    plan_block = _encode_plans(generations)
    input_text = (
        f"Situation: {situation}\n"
        f"The following are {len(generations)} independently generated plans "
        "for the same user profile."
    )
    test_case = LLMTestCase(input=input_text, actual_output=plan_block)

    eval_params = [SingleTurnParams.INPUT, SingleTurnParams.ACTUAL_OUTPUT]

    stability_metric = GEval(
        name="ServiceSetStability",
        evaluation_steps=_STABILITY_STEPS,
        evaluation_params=eval_params,
        model=judge_model,
        async_mode=False,
    )
    holistic_metric = GEval(
        name="HolisticConsistency",
        evaluation_steps=_HOLISTIC_STEPS,
        evaluation_params=eval_params,
        model=judge_model,
        async_mode=False,
    )

    stability_metric.measure(test_case)
    holistic_metric.measure(test_case)

    return {
        "service_stability": stability_metric.score,
        "holistic": holistic_metric.score,
        "reasons": {
            "service_stability": stability_metric.reason,
            "holistic": holistic_metric.reason,
        },
        "status": "judged",
        "note": None,
    }
