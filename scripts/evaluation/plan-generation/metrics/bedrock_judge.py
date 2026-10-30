"""The judge model every LLM-judged metric calls: a Claude model on AWS Bedrock."""

import json

import boto3

from metrics.retry import BadReply, TruncatedReply

# Reply token cap for every judge call. Relevance judges a whole plan in one
# call, with a rationale per task, so this has to fit the longest plan.
MAX_TOKENS = 4096


class BedrockJudge:
    """Calls a Claude model on Bedrock with one prompt and returns its text reply.

    Shared by all the judged metrics, so they all use the same model, region and
    settings.
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

    def generate(self, prompt: str) -> str:
        """Call Bedrock and return the model's text reply.

        Args:
            prompt: The full prompt text.

        Returns:
            The model's text reply.

        Raises:
            TruncatedReply: If the reply was cut off at ``MAX_TOKENS``.
            BadReply: If the reply has no text.
            botocore.exceptions.ClientError: And other boto3 errors, unwrapped,
                so ``retry.with_retries`` can tell which are worth retrying.
        """
        client = self.load_model()
        body = json.dumps(
            {
                "anthropic_version": "bedrock-2023-05-31",
                "max_tokens": MAX_TOKENS,
                "messages": [{"role": "user", "content": prompt}],
            }
        )
        response = client.invoke_model(modelId=self.model_id, body=body)
        payload = json.loads(response["body"].read())
        if payload.get("stop_reason") == "max_tokens":
            raise TruncatedReply(f"reply cut off at max_tokens={MAX_TOKENS}")
        chunks = [
            b["text"] for b in payload.get("content", []) if b.get("type") == "text"
        ]
        if not chunks:
            raise BadReply("no text content in Bedrock response")
        return "".join(chunks)
