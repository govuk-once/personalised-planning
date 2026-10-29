from botocore.exceptions import ClientError
from strands.event_loop._retry import ModelRetryStrategy
from strands.types.exceptions import ModelThrottledException


class BedrockRetryStrategy(ModelRetryStrategy):
    """Retry on throttling (default) and transient Bedrock service errors."""

    def is_retryable(self, exception: Exception) -> bool:
        if isinstance(exception, ModelThrottledException):
            return True
        if isinstance(exception, ClientError):
            code = exception.response["Error"]["Code"]
            return code.lower() == "serviceunavailableexception"
        return False
