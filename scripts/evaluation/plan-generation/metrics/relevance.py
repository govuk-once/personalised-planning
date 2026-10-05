"""Thin adapter: reuse run_app.py's relevance functions in the new harness.

The existing judge is kept verbatim — no DeepEval involved. The only
adaptation needed is wrapping the plan dict as ``{"plan": plan_dict}`` before
passing it to ``collect_relevance_tasks``, which traverses ``response["plan"]``.
"""

from typing import Any

import boto3

from run_app import (
    DEFAULT_RELEVANCE_MODEL,
    DEFAULT_RELEVANCE_REGION,
    collect_relevance_tasks,
    judge_plan_relevance,
    load_relevance_prompt,
)


def make_bedrock_client(region: str = DEFAULT_RELEVANCE_REGION) -> Any:
    """Create a boto3 bedrock-runtime client for the relevance judge.

    Args:
        region: AWS region for the Bedrock endpoint.

    Returns:
        A boto3 ``bedrock-runtime`` client.
    """
    return boto3.client("bedrock-runtime", region_name=region)


def score_relevance(
    generation: dict,
    client: Any,
    model_id: str,
    prompt_template: str,
    situation: str,
) -> dict:
    """Score relevance of tasks in one generation.

    Delegates to the existing ``judge_plan_relevance`` from ``run_app.py``.

    Args:
        generation: A generation dict with ``plan`` and ``context`` keys.
        client: A boto3 ``bedrock-runtime`` client.
        model_id: Bedrock model ID for the relevance judge.
        prompt_template: Template string from ``load_relevance_prompt()``.
        situation: The life-event situation string.

    Returns:
        Dict with ``tasks`` (list of judged task dicts) and ``status``.
    """
    plan = generation.get("plan") or {}
    context = generation.get("context") or {}

    # collect_relevance_tasks expects {"plan": plan_dict}
    tasks = collect_relevance_tasks({"plan": plan})
    if not tasks:
        return {"tasks": [], "status": "no_tasks"}

    judged = judge_plan_relevance(client, model_id, prompt_template, situation, context, tasks)
    return {"tasks": judged, "status": "judged"}
