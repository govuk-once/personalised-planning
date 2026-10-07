"""Relevance metric: are the plan's tasks relevant to the user's situation?

Custom Bedrock judge — no DeepEval, same logic and prompt as the original
run_app.py implementation so results remain comparable over time.

Verdicts per task:
- relevant   — a genuine current need for this person
- premature  — genuine but not yet needed (right topic, wrong timing)
- irrelevant — wrong topic entirely
"""

import json
import pathlib
from typing import Any

import boto3

DEFAULT_RELEVANCE_MODEL = "eu.anthropic.claude-sonnet-4-5-20250929-v1:0"
DEFAULT_RELEVANCE_REGION = "eu-west-1"

_METRICS_DIR = pathlib.Path(__file__).resolve().parent
RELEVANCE_PROMPT_PATH = _METRICS_DIR / "relevance_prompt.md"
_RELEVANCE_VERDICTS = {"relevant", "premature", "irrelevant"}


def make_bedrock_client(region: str = DEFAULT_RELEVANCE_REGION) -> Any:
    """Create a boto3 bedrock-runtime client.

    Args:
        region: AWS region for the Bedrock endpoint.

    Returns:
        A boto3 ``bedrock-runtime`` client.
    """
    return boto3.client("bedrock-runtime", region_name=region)


def load_relevance_prompt() -> str:
    """Read the relevance judge prompt template from its markdown file."""
    return RELEVANCE_PROMPT_PATH.read_text()


def collect_relevance_tasks(plan: dict) -> list[dict]:
    """Extract the task fields the relevance judge is allowed to see.

    Excludes the plan's ``reasoning`` field and any spine/truth data — only
    the task content itself goes to the judge.

    Args:
        plan: A plan dict (the ``"plan"`` key from the agent response).

    Returns:
        List of dicts with ``title``, ``summary``, ``gov_service_name``,
        ``url``, in plan order; only tasks with a ``gov_service_url`` included.
    """
    tasks = []
    for step in (plan or {}).get("steps") or []:
        for task in step.get("tasks") or []:
            url = task.get("gov_service_url") or ""
            if not url:
                continue
            tasks.append(
                {
                    "title": task.get("title") or task.get("task_title") or "",
                    "summary": task.get("summary") or "",
                    "gov_service_name": task.get("gov_service_name") or "",
                    "url": url,
                }
            )
    return tasks


def build_relevance_prompt(
    template: str, situation: str, context: dict, tasks: list[dict]
) -> str:
    """Fill the prompt template for one plan's relevance judgement.

    Args:
        template: Prompt text from ``load_relevance_prompt()``.
        situation: The life-event string.
        context: Dict from ``profile_context()``.
        tasks: List from ``collect_relevance_tasks()``.

    Returns:
        Completed prompt string.
    """
    numbered = "\n\n".join(
        f"{i}. {t['title']}\n"
        f"   Service: {t['gov_service_name']}\n"
        f"   Summary: {t['summary']}\n"
        f"   URL: {t['url']}"
        for i, t in enumerate(tasks)
    )
    return template.format(
        situation=situation,
        context=json.dumps(context, sort_keys=True),
        tasks=numbered,
    )


def _invoke_bedrock(
    client: Any, model_id: str, prompt: str, max_tokens: int = 2000
) -> str:
    """Call a Claude model on Bedrock and return its text output.

    Args:
        client: A boto3 ``bedrock-runtime`` client.
        model_id: Bedrock model or inference-profile ID.
        prompt: Full prompt text.
        max_tokens: Response token cap.

    Returns:
        The model's text response.

    Raises:
        RuntimeError: If the call fails or the response has no text.
    """
    body = json.dumps(
        {
            "anthropic_version": "bedrock-2023-05-31",
            "max_tokens": max_tokens,
            "temperature": 0,
            "messages": [{"role": "user", "content": prompt}],
        }
    )
    try:
        response = client.invoke_model(modelId=model_id, body=body)
        payload = json.loads(response["body"].read())
        chunks = [
            b["text"] for b in payload.get("content", []) if b.get("type") == "text"
        ]
        if not chunks:
            raise RuntimeError("no text content in Bedrock response")
        return "".join(chunks)
    except Exception as exc:  # noqa: BLE001
        raise RuntimeError(f"Bedrock call failed: {exc}") from exc


def _parse_relevance_response(text: str, n_tasks: int) -> list[dict]:
    """Parse the judge's JSON array, tolerating stray code fences.

    Any task the model didn't return a valid verdict for is marked
    ``"unjudged"`` rather than silently dropped.

    Args:
        text: Raw model output.
        n_tasks: Expected number of tasks, for filling gaps.

    Returns:
        List of length ``n_tasks`` with ``verdict`` and ``rationale`` per index.
    """
    cleaned = text.strip()
    if cleaned.startswith("```"):
        cleaned = cleaned.strip("`")
        cleaned = cleaned.split("\n", 1)[1] if "\n" in cleaned else cleaned
    by_index: dict[int, dict] = {}
    try:
        parsed = json.loads(cleaned)
        for item in parsed:
            i = item.get("index")
            verdict = item.get("verdict")
            if isinstance(i, int) and verdict in _RELEVANCE_VERDICTS:
                by_index[i] = {
                    "verdict": verdict,
                    "rationale": item.get("rationale", ""),
                }
    except (json.JSONDecodeError, TypeError, AttributeError):
        pass
    return [
        by_index.get(
            i, {"verdict": "unjudged", "rationale": "could not parse judge output"}
        )
        for i in range(n_tasks)
    ]


def judge_plan_relevance(
    client: Any,
    model_id: str,
    prompt_template: str,
    situation: str,
    context: dict,
    tasks: list[dict],
) -> list[dict]:
    """Run the relevance judge over one plan's tasks.

    Args:
        client: A boto3 ``bedrock-runtime`` client.
        model_id: Bedrock model or inference-profile ID.
        prompt_template: Prompt text from ``load_relevance_prompt()``.
        situation: The life-event string.
        context: Dict from ``profile_context()``.
        tasks: List from ``collect_relevance_tasks()``.

    Returns:
        List of dicts merging each task with its verdict and rationale.
    """
    if not tasks:
        return []
    prompt = build_relevance_prompt(prompt_template, situation, context, tasks)
    text = _invoke_bedrock(client, model_id, prompt)
    verdicts = _parse_relevance_response(text, len(tasks))
    return [{**task, **verdict} for task, verdict in zip(tasks, verdicts, strict=True)]


def score_relevance(
    generation: dict,
    client: Any,
    model_id: str,
    prompt_template: str,
    situation: str,
) -> dict:
    """Score the relevance of tasks in one generation.

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

    tasks = collect_relevance_tasks(plan)
    if not tasks:
        return {"tasks": [], "status": "no_tasks"}

    judged = judge_plan_relevance(
        client, model_id, prompt_template, situation, context, tasks
    )
    return {"tasks": judged, "status": "judged"}
