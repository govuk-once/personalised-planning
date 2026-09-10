#!/usr/bin/env python3
import json
import time
import uuid

from bedrock_agentcore import BedrockAgentCoreApp, RequestContext
from dotenv import load_dotenv
from log_utils import StructuredLogger
from pydantic import BaseModel
from secrets_manager import load_secrets_into_env

INSTANCE_ID = str(uuid.uuid4())


load_dotenv()  # must come before secrets_manager call

load_secrets_into_env("planner-agent", region="eu-west-2")

from planner_logic import run_planner  # noqa: E402

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
    situation = data.get("situation") or data.get("prompt") or ""
    user_context = data.get("user_context")
    auth_token = None
    if context and context.request_headers:
        auth_token = context.request_headers.get("Authorization")

    output = await run_planner(
        situation=situation,
        auth_token=auth_token,
        user_context=user_context,
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
        "INFO", "Starting Planner AgentCore app", instance_id=INSTANCE_ID, step="startup"
    )
    app.run()
