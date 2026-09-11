#!/usr/bin/env python3
import json
import time
import uuid

from bedrock_agentcore import BedrockAgentCoreApp, RequestContext
from dotenv import load_dotenv
from pydantic import BaseModel
from shared.log_utils import StructuredLogger
from shared.secrets_manager import load_secrets_into_env

INSTANCE_ID = str(uuid.uuid4())


load_dotenv()  # must come before secrets_manager call

# Reuse the planner's secret — both runtimes share the same Secrets Manager entry.
load_secrets_into_env("planner-agent", region="eu-west-2")

from chat_logic import run_chat  # noqa: E402

app = BedrockAgentCoreApp()

startup_logger = StructuredLogger(session_id="startup", user_id="startup", agent_name="startup")


class InvocationResponse(BaseModel):
    output: dict


@app.entrypoint
async def main(payload: dict | None = None, context: RequestContext | None = None):
    session_id = (payload or {}).get("session_id", "unknown")
    user_id = ((payload or {}).get("user_context") or {}).get("user_id", "unknown")
    agentcore_runtime_id = (payload or {}).get("agentcore_runtime_id", "unknown")

    try:
        logger = StructuredLogger(
            session_id=session_id, user_id=user_id, agent_name=agentcore_runtime_id
        )
    except Exception as e:
        startup_logger.log("ERROR", "Failed to create logger", error=str(e))
        raise e

    logger.log(
        "INFO",
        "Payload received",
        instance_id=INSTANCE_ID,
        payload=json.dumps(payload) if isinstance(payload, dict) else None,
        step="entrypoint",
    )
    request_start = time.perf_counter()

    data = payload or {}
    messages = data.get("messages") or []

    output = await run_chat(
        messages=messages,
        logger=logger,
    )

    response = InvocationResponse(output=output)
    total_elapsed = round(time.perf_counter() - request_start, 2)
    logger.log(
        "INFO",
        "Request complete",
        total_elapsed_s=total_elapsed,
        instance_id=INSTANCE_ID,
        step="entrypoint",
    )
    logger.log(
        "INFO",
        f"Output generated: {list(response.output.keys())}",
        instance_id=INSTANCE_ID,
        step="entrypoint",
    )
    return response


if __name__ == "__main__":
    startup_logger.log(
        "INFO", "Starting Chat AgentCore app", instance_id=INSTANCE_ID, step="startup"
    )
    app.run()
