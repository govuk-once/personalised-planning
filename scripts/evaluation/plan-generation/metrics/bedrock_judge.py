"""DeepEval judge-model factory backed by AWS Bedrock via boto3."""

import json
import re

import boto3
from deepeval.models import DeepEvalBaseLLM


class BedrockJudge(DeepEvalBaseLLM):
    """Wraps boto3 bedrock-runtime for use as a DeepEval judge model.

    Implements ``generate(prompt, schema=None)``. When a Pydantic schema class
    is supplied the prompt is augmented with JSON-schema instructions and the
    response is parsed with ``schema.model_validate_json()``, returning a
    schema instance directly so DeepEval's ``generate_with_schema_and_extract``
    can short-circuit straight to ``extract_schema(result)`` without a second
    JSON parse.
    """

    def __init__(self, model_id: str, region: str) -> None:
        """Initialise with a Bedrock model ID and AWS region."""
        self.model_id = model_id
        self.region = region
        self._client = None

    def load_model(self):
        """Lazy-initialise the boto3 client."""
        if self._client is None:
            self._client = boto3.client("bedrock-runtime", region_name=self.region)
        return self._client

    def generate(self, prompt: str, schema=None):
        """Call Bedrock and return a string or a parsed Pydantic schema instance.

        Args:
            prompt: The full prompt text.
            schema: Optional Pydantic model class. When supplied, the response
                is parsed and returned as an instance of that class.

        Returns:
            A Pydantic model instance when ``schema`` is provided, else the raw
            response string.
        """
        self.load_model()

        full_prompt = prompt
        if schema is not None:
            schema_json = json.dumps(schema.model_json_schema(), indent=2)
            full_prompt = (
                f"{prompt}\n\n"
                f"Respond with a JSON object that strictly matches this schema:\n"
                f"```json\n{schema_json}\n```\n"
                "Return ONLY the JSON object, no extra text or explanation."
            )

        body = json.dumps(
            {
                "anthropic_version": "bedrock-2023-05-31",
                "max_tokens": 4096,
                "temperature": 0,
                "messages": [{"role": "user", "content": full_prompt}],
            }
        )
        response = self._client.invoke_model(modelId=self.model_id, body=body)
        payload = json.loads(response["body"].read())
        chunks = [
            b["text"] for b in payload.get("content", []) if b.get("type") == "text"
        ]
        text = "".join(chunks)

        if schema is None:
            return text

        # Strip any stray code fences before parsing
        cleaned = text.strip()
        if cleaned.startswith("```"):
            cleaned = re.sub(r"^```[a-z]*\n?", "", cleaned)
            cleaned = re.sub(r"\n?```$", "", cleaned.strip())
        return schema.model_validate_json(cleaned.strip())

    async def a_generate(self, prompt: str, schema=None):
        """Async shim — delegates to synchronous ``generate``.

        Acceptable at the low N values this harness uses.
        """
        return self.generate(prompt, schema=schema)

    def get_model_name(self) -> str:
        """Return the Bedrock model ID."""
        return self.model_id
