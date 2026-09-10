"""
Utilties for accessing Bedrock LLM models.

Two ways to call the model:

  invoke(prompt)                  free text via invoke_model.

  converse_structured(prompt,     forced tool use via the Converse API. The
                      tool)       model must call the named tool, so the
                                  response is already a parsed dict. No code
                                  fences to strip, no brace matching, no
                                  schema coercion, no parse-failure path.

Prefer converse_structured for anything whose output you aggregate. The
invoke + parse route can only fail *silently* — an unparseable response
becomes a default-valued object that scores like a real result.
"""

from __future__ import annotations

import json
import random
import time
from typing import Any

DEFAULT_MODEL_ID = "eu.anthropic.claude-sonnet-5"
DEFAULT_REGION = "eu-west-2"

RETRYABLE = ("Throttling", "TooManyRequests", "Timeout", "ServiceUnavailable")


class BedrockClaude:
    """Thin wrapper over bedrock-runtime."""

    def __init__(
        self,
        model_id: str = DEFAULT_MODEL_ID,
        region: str = DEFAULT_REGION,
        profile: str | None = None,
        temperature: float | None = None,
        max_tokens: int = 4096,
        max_retries: int = 5,
    ):
        self.model_id = model_id
        self.region = region
        self.profile = profile
        self.temperature = temperature
        self.max_tokens = max_tokens
        self.max_retries = max_retries
        self.client = None
        self.load_model()

    def load_model(self) -> None:
        # Imported here rather than at module scope so --dry-run works in an
        # environment without boto3 installed.
        import boto3
        from botocore.config import Config

        session = boto3.Session(profile_name=self.profile) if self.profile else boto3.Session()
        self.client = session.client(
            "bedrock-runtime",
            region_name=self.region,
            config=Config(retries={"max_attempts": 3, "mode": "adaptive"}, read_timeout=300),
        )

    def get_model_name(self) -> str:
        return self.model_id

    # ----------------------------------------------------------------------

    def _with_retry(self, call):
        """Retry throttling and timeouts with jittered backoff. Everything else raises."""
        last_error: Exception | None = None
        for attempt in range(self.max_retries):
            try:
                return call()
            except Exception as error:  # noqa: BLE001
                if not any(token in type(error).__name__ for token in RETRYABLE):
                    raise
                last_error = error
                time.sleep(min(2**attempt + random.random(), 30))
        raise RuntimeError(f"exhausted {self.max_retries} retries: {last_error}")

    def invoke(self, prompt: str, system: str | None = None) -> str:
        """Free-text completion via invoke_model."""

        def call() -> str:
            body: dict[str, Any] = {
                "anthropic_version": "bedrock-2023-05-31",
                "messages": [{"role": "user", "content": prompt}],
                "max_tokens": self.max_tokens,
            }
            if self.temperature is not None:
                body["temperature"] = self.temperature
            if system:
                body["system"] = system
            response = self.client.invoke_model(modelId=self.model_id, body=json.dumps(body))
            return json.loads(response["body"].read())["content"][0]["text"]

        return self._with_retry(call)

    def converse_structured(
        self,
        prompt: str,
        tool: dict[str, Any],
        system: str | None = None,
    ) -> tuple[dict[str, Any], dict[str, int]]:
        """
        Call the model with toolChoice pinned to `tool`, so the response is a
        validated tool input rather than prose that happens to contain JSON.

        `tool` is a Converse toolSpec:
            {"toolSpec": {"name": ..., "description": ...,
                          "inputSchema": {"json": {<json schema>}}}}

        Returns (tool_input, usage).
        """
        tool_name = tool["toolSpec"]["name"]

        inference_config: dict[str, Any] = {"maxTokens": self.max_tokens}
        if self.temperature is not None:
            inference_config["temperature"] = self.temperature

        def call() -> tuple[dict[str, Any], dict[str, int]]:
            response = self.client.converse(
                modelId=self.model_id,
                system=[{"text": system}] if system else [],
                messages=[{"role": "user", "content": [{"text": prompt}]}],
                toolConfig={"tools": [tool], "toolChoice": {"tool": {"name": tool_name}}},
            )
            for block in response["output"]["message"]["content"]:
                if "toolUse" in block:
                    return block["toolUse"]["input"], response.get("usage", {})
            # Reachable only if the model stopped early (e.g. max_tokens hit
            # mid-tool-call). Raise rather than return an empty result — a
            # silent default here would be scored as a real judgement.
            raise RuntimeError(
                f"no toolUse block returned (stopReason={response.get('stopReason')})"
            )

        return self._with_retry(call)
