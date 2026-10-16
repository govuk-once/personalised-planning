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
    client, runtime_arn: str, situation: str, context: dict, max_attempts: int
) -> tuple[dict | None, str | None]:
    """Get one plan from the hosted agent, retrying transient failures.

    Waits 5s, 10s, 20s... (capped at 60s) between attempts. Retrying is safe: the
    planner has no side effects and every call uses a fresh session.

    Args:
        client: Client from ``run_app.make_agent_client``.
        runtime_arn: ARN of the deployed planner runtime.
        situation: The profile's situation sentence from ``profile_situation``.
        context: The user_context dict from ``profile_context``.
        max_attempts: Total tries, including the first.

    Returns:
        ``(generation, None)`` on success, or ``(None, last_error)``. A
        generation holds the ``plan`` with the ``situation`` and ``context``
        the planner was given.
    """
    from run_app import call_api

    error = "no attempts made"
    for attempt in range(1, max_attempts + 1):
        try:
            plan = call_api(client, runtime_arn, situation, context).get("plan")
        except RuntimeError as exc:
            error = str(exc)
            if not is_transient(exc):
                return None, error
        else:
            if plan:
                return {"plan": plan, "situation": situation, "context": context}, None
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
