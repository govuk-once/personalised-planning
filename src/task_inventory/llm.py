"""
LLM call helper: structured Bedrock calls with caching, normalisation, and retries

Thin wrapper around BedrockClaude.converse_structured() that adds:
- Vocabulary normalisation (schema.normalise) before Pydantic validation.
- JSON double-encoding repair (rare LLM quirk where the tool output is a JSON string).
- Retry loop with error feedback injected into the prompt.
- Disk-based JSON cache keyed by stage + prompt version + model + input hash.

Key functions:
- call_structured(model_class, prompt, system, ...)
      Makes a Bedrock tool-use call and returns CallResult[T].  All callers
      (drafts, clustering) use this function.
- make_cache_key(stage, prompt_version, model_id, payload)
      Produces a stable cache key string; payload is JSON-serialised and hashed.

CallResult fields: value (parsed model or None), errors, usage, raw, from_cache.

Environment variables:
- ANTHROPIC_MODEL  Bedrock model ID (default: eu.anthropic.claude-sonnet-5).
- AWS_REGION       AWS region (default: eu-west-2).

Assumptions:
- AWS credentials must be available in the environment (e.g. via aws-vault or
  instance role).
- Cache files are written to  data/cache/<stage>/<hash16>.json  relative to CWD.
  Delete this directory to force all LLM calls to re-run.
- Cache entries are invalidated automatically when the model ID or prompt version
  changes (both are part of the key).
"""

import hashlib
import json
import os
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ValidationError

from src.task_inventory.schema import normalise
from src.utils.bedrock_client import BedrockClaude


@dataclass
class CallResult[T: BaseModel]:
    """Result of an LLM call with structured output"""

    value: T | None
    errors: list[str]
    usage: dict
    raw: Any
    from_cache: bool = False


def call_structured[T: BaseModel](
    model_class: type[T],
    prompt: str,
    system: str,
    *,
    max_tokens: int = 4096,
    check: Callable[[T], list[str]] | None = None,
    retries: int = 1,
    cache_key: str | None = None,
    model_id: str | None = None,
    region: str | None = None,
) -> CallResult[T]:
    """
    Call LLM with structured output, handling:
    - JSON unwrapping (if LLM returns string instead of dict)
    - Normalisation (vocabulary synonyms)
    - Validation
    - Custom checks
    - Retries with error feedback
    - Caching

    Args:
        model_class: Pydantic model for output
        prompt: User prompt
        system: System prompt
        max_tokens: Max output tokens
        check: Optional validation function returning list of error strings
        retries: Number of retries after first failure (default 1)
        cache_key: If provided, cache the result under this key
        model_id: Bedrock model ID
        region: AWS region

    Returns:
        CallResult with value (if successful) or errors
    """
    model_id = model_id or os.getenv("ANTHROPIC_MODEL", "eu.anthropic.claude-sonnet-5")
    region = region or os.getenv("AWS_REGION", "eu-west-2")

    # Check cache first
    if cache_key:
        cached = _load_from_cache(cache_key)
        if cached:
            try:
                value = model_class.model_validate(cached["value"])
                return CallResult(
                    value=value,
                    errors=[],
                    usage=cached.get("usage", {}),
                    raw=cached.get("raw"),
                    from_cache=True,
                )
            except Exception:
                # Cache corrupt or schema changed, proceed with call
                pass

    # Tool spec for structured output
    tool_spec = {
        "toolSpec": {
            "name": model_class.__name__.lower(),
            "description": f"Output {model_class.__name__}",
            "inputSchema": {"json": model_class.model_json_schema()},
        }
    }

    client = BedrockClaude(model_id=model_id, region=region, max_tokens=max_tokens)

    errors: list[str] = []
    current_prompt = prompt
    attempts = 1 + retries

    for attempt in range(attempts):
        try:
            # Make call
            result, usage = client.converse_structured(
                prompt=current_prompt, tool=tool_spec, system=system
            )

            # Unwrap if LLM returned JSON as string
            if isinstance(result, str):
                result = json.loads(result)

            # Handle double-encoding (rare but seen in V2)
            result_key = (
                list(model_class.model_fields.keys())[0] if model_class.model_fields else None
            )
            if result_key and isinstance(result.get(result_key), str):
                result[result_key] = json.loads(result[result_key])

            # Normalise vocabulary fields
            result_normalised = normalise(result)

            # Validate
            value = model_class.model_validate(result_normalised)

            # Custom checks
            if check:
                check_errors = check(value)
                if check_errors:
                    errors.extend(check_errors)
                    if attempt < attempts - 1:
                        # Retry with errors in prompt
                        error_msg = "\n".join(f"- {e}" for e in check_errors)
                        current_prompt = f"{prompt}\n\n**Errors from previous attempt:**\n{error_msg}\n\nPlease fix these errors."
                        continue
                    else:
                        # Last attempt failed
                        return CallResult(value=None, errors=errors, usage=usage, raw=result)

            # Success!
            call_result = CallResult(value=value, errors=[], usage=usage, raw=result)

            # Cache if key provided
            if cache_key:
                _save_to_cache(
                    cache_key, {"value": result_normalised, "usage": usage, "raw": result}
                )

            return call_result

        except ValidationError as e:
            error_msgs = [f"{err['loc']}: {err['msg']}" for err in e.errors()]
            errors.extend(error_msgs)

            if attempt < attempts - 1:
                # Retry with validation errors
                error_msg = "\n".join(f"- {msg}" for msg in error_msgs)
                current_prompt = f"{prompt}\n\n**Validation errors from previous attempt:**\n{error_msg}\n\nPlease fix these errors."
            else:
                # Last attempt failed
                return CallResult(
                    value=None,
                    errors=errors,
                    usage=usage if "usage" in locals() else {},
                    raw=result if "result" in locals() else None,
                )

        except json.JSONDecodeError as e:
            errors.append(f"JSON decode error: {e}")
            if attempt < attempts - 1:
                current_prompt = f"{prompt}\n\n**Error:** Invalid JSON in previous response. Please return valid JSON."
            else:
                return CallResult(value=None, errors=errors, usage={}, raw=None)

        except Exception as e:
            errors.append(f"Unexpected error: {e}")
            if attempt >= attempts - 1:
                return CallResult(value=None, errors=errors, usage={}, raw=None)

    # Should not reach here
    return CallResult(value=None, errors=errors or ["Unknown error"], usage={}, raw=None)


def make_cache_key(stage: str, prompt_version: str, model_id: str, payload: dict) -> str:
    """
    Create cache key from stage, prompt version, model and input payload.

    Args:
        stage: "drafts" or "clusters"
        prompt_version: e.g. "v1"
        model_id: Bedrock model ID
        payload: Input data (will be serialized and hashed)

    Returns:
        Cache key string
    """
    payload_str = json.dumps(payload, sort_keys=True)
    hash_input = f"{prompt_version}|{model_id}|{payload_str}"
    key_hash = hashlib.sha1(hash_input.encode()).hexdigest()
    return f"{stage}/{key_hash[:16]}"


def _load_from_cache(cache_key: str) -> dict | None:
    """Load cached result if exists"""
    cache_path = Path("data/cache") / f"{cache_key}.json"
    if cache_path.exists():
        try:
            with open(cache_path) as f:
                return json.load(f)
        except Exception:
            return None
    return None


def _save_to_cache(cache_key: str, data: dict) -> None:
    """Save result to cache"""
    cache_path = Path("data/cache") / f"{cache_key}.json"
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    try:
        with open(cache_path, "w") as f:
            json.dump(data, f, indent=2)
    except Exception:
        pass  # Cache save failures are non-fatal
