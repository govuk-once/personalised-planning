import json
import os
from typing import Any

import boto3


def load_secrets_into_env(secret_id: str, region: str | None = None) -> None:
    client = boto3.client(
        "secretsmanager",
        region_name=region
        or os.getenv("AWS_REGION")
        or os.getenv("AWS_DEFAULT_REGION")
        or "eu-west-1",
    )
    resp: dict[str, Any] = client.get_secret_value(SecretId=secret_id)

    secret_str = resp.get("SecretString")
    if not secret_str:
        raise RuntimeError("Secret has no SecretString")

    data = json.loads(secret_str)
    if not isinstance(data, dict):
        raise RuntimeError("SecretString must be a JSON object")

    for k, v in data.items():
        if v is None:
            continue
        if not os.getenv(k):
            os.environ[k] = str(v)
