"""Faithfulness metric: does the plan stay faithful to its MCP retrieval context?

Uses DeepEval's FaithfulnessMetric. Each generation is scored independently
against its own tool-call results (the retrieval context captured during that
run). The plan's ``reasoning`` field is excluded — the judge grades factual
claims, not the agent's self-justification.
"""

import json
from typing import Any

from deepeval.metrics import FaithfulnessMetric
from deepeval.test_case import LLMTestCase


def _serialize_plan(plan: dict) -> str:
    """Serialise user-facing plan fields, excluding ``Plan.reasoning``.

    Args:
        plan: A plan dict from the agent (as returned by ``runner.run()``).

    Returns:
        A readable multi-line string covering all task-level claims.
    """
    lines = []
    plan_title = plan.get("title", "")
    if plan_title:
        lines.append(f"Plan: {plan_title}")
    plan_summary = plan.get("summary", "")
    if plan_summary:
        lines.append(f"Summary: {plan_summary}")

    for step in plan.get("steps", []):
        lines.append(f"\nStep: {step.get('title', '')}")
        if step.get("summary"):
            lines.append(f"  {step['summary']}")
        for task in step.get("tasks", []):
            lines.append(f"  Task: {task.get('title', '')}")
            if task.get("summary"):
                lines.append(f"    Summary: {task['summary']}")
            svc = task.get("gov_service_name", "")
            url = task.get("gov_service_url", "")
            if svc or url:
                lines.append(f"    Service: {svc} ({url})")
            if task.get("deadline"):
                lines.append(f"    Deadline: {task['deadline']}")
            if task.get("cost") is not None:
                lines.append(f"    Cost: {task['cost']}")
            if task.get("grant"):
                lines.append(f"    Grant: {task['grant']}")
            if task.get("what_to_expect"):
                lines.append(f"    What to expect: {task['what_to_expect']}")
            if task.get("requirements"):
                lines.append(f"    Requirements: {', '.join(task['requirements'])}")

    return "\n".join(lines)


def score_faithfulness(
    generation: dict,
    judge_model: Any,
    situation: str,
) -> dict:
    """Score one generation's faithfulness to its retrieval context.

    Args:
        generation: A dict with ``plan``, ``retrieval_context``, and ``context``
            (as returned by ``generation.generate_plans``).
        judge_model: A ``BedrockJudge`` (or any ``DeepEvalBaseLLM``) instance.
        situation: The life-event situation string.

    Returns:
        Dict with ``score`` (float or None), ``reason`` (str), and ``status``
        (``"judged"`` or ``"unjudged"``).
    """
    retrieval_context = generation.get("retrieval_context") or []
    if not retrieval_context:
        return {
            "score": None,
            "reason": "no retrieval context captured for this generation",
            "status": "unjudged",
        }

    plan = generation.get("plan") or {}
    actual_output = _serialize_plan(plan)
    context = generation.get("context") or {}

    input_text = f"Situation: {situation}"
    if context:
        input_text += f"\nUser context: {json.dumps(context, sort_keys=True)}"

    test_case = LLMTestCase(
        input=input_text,
        actual_output=actual_output,
        retrieval_context=retrieval_context,
    )
    metric = FaithfulnessMetric(
        model=judge_model,
        include_reason=True,
        async_mode=False,
    )
    metric.measure(test_case)

    return {
        "score": metric.score,
        "reason": metric.reason,
        "status": "judged",
    }
