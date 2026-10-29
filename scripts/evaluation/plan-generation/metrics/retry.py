"""Retry judge calls that fail for a reason a second try may fix."""

import json
import sys
import time
from collections.abc import Callable

from botocore.exceptions import (
    ClientError,
    ConnectionError as BotoConnectionError,
    CredentialRetrievalError,
    EndpointConnectionError,
    HTTPClientError,
    NoCredentialsError,
    PartialCredentialsError,
    SSOError,
    TokenRetrievalError,
)

# Tries after the first. A judge call is made at most RETRIES + 1 times.
RETRIES = 2

# Error codes that mean the credentials or permissions are wrong, so no later
# call will work either.
_FATAL_CODES = frozenset(
    {
        "AccessDeniedException",
        "ExpiredTokenException",
        "ExpiredToken",
        "UnrecognizedClientException",
        "InvalidSignatureException",
        "InvalidClientTokenId",
    }
)
# Raised by boto3 itself, before a request is sent, when it has no usable
# credentials (including an expired SSO login).
_FATAL_ERRORS = (
    NoCredentialsError,
    PartialCredentialsError,
    CredentialRetrievalError,
    TokenRetrievalError,
    SSOError,
)

# Error codes InvokeModel can return that are worth retrying.
_TRANSIENT_CODES = frozenset(
    {
        "ThrottlingException",
        "ModelTimeoutException",
        "ServiceUnavailableException",
        "InternalServerException",
        "ModelNotReadyException",
    }
)


class BadReply(Exception):
    """The judge replied, but with nothing that can be used."""


class FatalJudgeError(Exception):
    """The judge cannot be used: access is denied or credentials are missing or expired.

    Unlike other failed calls this is not marked ``unjudged``. It ends ``score``,
    because every later call would fail the same way.
    """


def _cause(exc: Exception) -> BaseException:
    """The underlying error, which a wrapping ``RuntimeError`` has on ``__cause__``."""
    return exc.__cause__ or exc


def is_fatal(exc: Exception) -> bool:
    """Whether an error means the credentials or permissions are wrong.

    Covers access denied, expired or invalid credentials, and boto3 having no
    usable credentials at all (including an expired SSO login).

    Args:
        exc: The error from one attempt.

    Returns:
        True if no later call can succeed until the credentials are fixed.
    """
    cause = _cause(exc)
    if isinstance(cause, ClientError):
        return cause.response.get("Error", {}).get("Code") in _FATAL_CODES
    return isinstance(cause, _FATAL_ERRORS)


def is_transient(exc: Exception) -> bool:
    """Whether a failed judge call is worth retrying.

    Retries throttling, server errors, timeouts, connection errors and replies
    that were empty or not valid. Anything else (bad request, unknown errors) is
    treated as permanent so it fails at once instead of waiting through retries.
    Fatal errors (see ``is_fatal``) are not retried either.

    Args:
        exc: The error from one attempt. A ``RuntimeError`` that wraps the
            underlying error has it on ``__cause__``.

    Returns:
        True if another attempt might succeed.
    """
    if isinstance(exc, BadReply):
        return True
    cause = _cause(exc)
    if isinstance(cause, ClientError):
        return cause.response.get("Error", {}).get("Code") in _TRANSIENT_CODES
    return isinstance(
        cause,
        BotoConnectionError
        | EndpointConnectionError
        | HTTPClientError
        | json.JSONDecodeError
        | OSError,
    )


def _reason(exc: Exception) -> str:
    """A few words saying why an attempt failed, for the progress line."""
    if isinstance(exc, BadReply):
        return str(exc)
    cause = _cause(exc)
    if isinstance(cause, ClientError):
        return cause.response.get("Error", {}).get("Code", "ClientError")
    return type(cause).__name__


def with_retries[T](attempt: Callable[[], T], what: str) -> T:
    """Call ``attempt()``, trying again after a transient failure.

    Waits 5s, then 10s, between tries and prints each retry to stderr. Retrying
    is safe: a judge call has no side effects.

    Args:
        attempt: One try at the whole call, including checking the reply. It
            raises ``BadReply`` when the reply is unusable.
        what: Names the call in the progress line, e.g. ``"relevance judge"``.

    Returns:
        Whatever ``attempt`` returns.

    Raises:
        FatalJudgeError: At once, with no retry, if access is denied or the
            credentials are missing or expired.
        Exception: Otherwise the last error, once ``RETRIES`` retries are used
            up, or at once if it is not transient.
    """
    retry = 0
    while True:
        try:
            return attempt()
        except Exception as exc:
            if is_fatal(exc):
                raise FatalJudgeError(f"{what}: {_cause(exc)}") from exc
            if retry >= RETRIES or not is_transient(exc):
                raise
            retry += 1
            wait = min(60, 5 * 2 ** (retry - 1))
            print(
                f"  {what}: {_reason(exc)}; retry {retry}/{RETRIES} in {wait}s",
                file=sys.stderr,
            )
            time.sleep(wait)
