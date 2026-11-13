"""Get one plan from the hosted planner agent, retrying transient failures."""

import json
import sys
import time

from botocore.exceptions import (
    ClientError,
    ConnectionError as BotoConnectionError,
    EndpointConnectionError,
    HTTPClientError,
)

# Error codes InvokeAgentRuntime can return that are worth retrying.
_TRANSIENT_CODES = frozenset(
    {
        "ThrottlingException",
        "InternalServerException",
        "RetryableConflictException",
        "RuntimeClientError",
    }
)


def is_transient(exc: RuntimeError) -> bool:
    """Whether a failed agent call is worth retrying.

    Retries throttling, server errors, timeouts, connection errors and replies
    that were not valid. Anything else (access denied, bad request, missing or
    expired credentials, unknown errors) is treated as permanent so it fails at
    once instead of looping.

    Args:
        exc: The RuntimeError raised by ``run_app.call_api``; the underlying
            error is on ``__cause__``.

    Returns:
        True if another attempt might succeed.
    """
    cause = exc.__cause__
    if isinstance(cause, ClientError):
        return cause.response.get("Error", {}).get("Code") in _TRANSIENT_CODES
    if isinstance(
        cause, BotoConnectionError | EndpointConnectionError | HTTPClientError | OSError
    ):
        return True
    # No cause: the agent replied but with no usable output. A bad JSON body is
    # the same kind of failure.
    return cause is None or isinstance(cause, json.JSONDecodeError)


def generate_one(
    client,
    runtime_arn: str,
    situation: str,
    context: dict,
    max_attempts: int,
    session_id: str | None = None,
) -> tuple[dict | None, str | None]:
    """Get one plan from the hosted agent, retrying transient failures.

    Waits 5s, 10s, 20s... (capped at 60s) between attempts. Retrying is safe: the
    planner has no side effects and keeps nothing between calls in a session.

    Args:
        client: Client from ``run_app.make_agent_client``.
        runtime_arn: ARN of the deployed planner runtime.
        situation: The profile's situation sentence from ``profile_situation``.
        context: The user_context dict from ``profile_context``.
        max_attempts: Total tries, including the first.
        session_id: AgentCore session to run in, recorded so AgentCore
            Evaluations can find the run (``metrics.agentcore``).

    Returns:
        ``(generation, None)`` on success, or ``(None, last_error)``. A
        generation holds the ``plan`` with the ``situation`` and ``context``
        the planner was given, and the ``session_id``.
    """
    from run_app import call_api

    error = "no attempts made"
    for attempt in range(1, max_attempts + 1):
        try:
            reply = call_api(client, runtime_arn, situation, context, session_id)
            plan = reply.get("plan")
        except RuntimeError as exc:
            error = str(exc)
            if not is_transient(exc):
                return None, error
        else:
            if plan:
                generation = {"plan": plan, "situation": situation, "context": context}
                return {**generation, "session_id": session_id}, None
            error = "no plan in response"

        if attempt < max_attempts:
            wait = min(60, 5 * 2 ** (attempt - 1))
            print(
                f"  attempt {attempt}/{max_attempts} failed ({error}); "
                f"retrying in {wait}s",
                file=sys.stderr,
            )
            time.sleep(wait)
    return None, error
