import json
import os
import uuid
from datetime import UTC, datetime
from typing import Any
from agent_mock_response import mock_response

import boto3
import httpx
from botocore.config import Config
from botocore.exceptions import ClientError
from fastapi import FastAPI, HTTPException, Request
from fastapi.concurrency import run_in_threadpool
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from log_utils import StructuredLogger

# --- Configuration ---
# Set LOCAL_MODE=true to call a locally running agent process/container,
# instead of the deployed AgentCore runtime.
LOCAL_MODE = os.getenv("LOCAL_MODE", "false").lower() == "true"
AWS_REGION = os.getenv("AWS_DEFAULT_REGION", "eu-west-2")

# Local mode: where the locally-running agent's /invocations endpoint lives.
# This is the same contract BedrockAgentCoreApp.run() serves, so it works
# whether the agent is running as a bare process or inside a local container.
AGENT_URL = os.getenv("AGENT_URL", "http://localhost:8080/invocations")

# AgentCore mode: ARN of the deployed agent runtime (from `agentcore launch`
# output, or the bedrock_agentcore: section of .bedrock_agentcore.yaml).
AGENT_RUNTIME_ARN = os.getenv("AGENT_RUNTIME_ARN")
AGENT_ENDPOINT_NAME = os.getenv("AGENT_ENDPOINT_NAME")

app = FastAPI(title="Planner Backend", version="1.0.0")

# boto3 client is thread-safe and cheap to reuse across requests.
_agentcore_client = None

# MIDDLEWARE
# CORS remains unchanged
# origins currently hardcoded and set to localhost:3000 for development - to be replaced by env vars later once known
origins = ["http://localhost:3000"]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


def _get_agentcore_client():
    global _agentcore_client
    if _agentcore_client is None:
        _agentcore_client = boto3.client(
            "bedrock-agentcore",
            region_name=AWS_REGION,
            config=Config(
                read_timeout=300,
                connect_timeout=10,
                retries={"max_attempts": 1},
            ),
        )
    return _agentcore_client


# TODO: once agent/backend share a schema package (see JIRA-XXXX), validate
# `output` against the shared ResultPayload model in agent/app/structured_outputs.py instead of passing
# through unchecked.
def unwrap_agent_output(result: dict[str, Any], logger: StructuredLogger) -> dict[str, Any]:
    output = result.get("output", result) or {}

    if not isinstance(output, dict) or ("plan" not in output and "agent_help" not in output):
        logger.log(
            "WARN",
            "Agent output missing expected keys",
            keys=list(output.keys()) if isinstance(output, dict) else type(output).__name__,
            step="unwrap",
        )

    return {
        "plan": output.get("plan"),
        "agent_help": output.get("agent_help"),
        "timestamp": datetime.now(UTC).isoformat(),
        "status": "success",
    }


class PlanRequest(BaseModel):
    situation: str = Field(
        ..., description="The user's current situation or query to create a plan for"
    )
    user_context: dict[str, Any] | None = Field(
        default=None, description="Optional additional user facts, such as location"
    )


class HealthCheck(BaseModel):
    status: str = "OK"


@app.get("/health")
def healthcheck():
    return HealthCheck()


@app.get("/mock")
def mock():
    return mock_response()


async def _invoke_local(
    session_id: str,
    situation: str,
    user_context: dict[str, Any] | None,
    logger: StructuredLogger,
) -> dict[str, Any]:
    payload = {
        "session_id": session_id,
        "situation": situation,
        "user_context": user_context,
    }

    logger.log("INFO", "Calling local planner agent", agent_url=AGENT_URL, step="agent_call")
    async with httpx.AsyncClient() as client:
        resp = await client.post(AGENT_URL, json=payload, timeout=480.0)
        resp.raise_for_status()
        return resp.json()


async def _invoke_agentcore(
    session_id: str,
    situation: str,
    user_context: dict[str, Any] | None,
    logger: StructuredLogger,
) -> dict[str, Any]:
    if not AGENT_RUNTIME_ARN:
        raise RuntimeError("AGENT_RUNTIME_ARN environment variable is required in AgentCore mode.")

    payload = json.dumps(
        {
            "session_id": session_id,
            "situation": situation,
            "user_context": user_context,
        }
    ).encode()

    logger.log(
        "INFO", "Calling AgentCore runtime", runtime_arn=AGENT_RUNTIME_ARN, step="agent_call"
    )

    client = _get_agentcore_client()
    # boto3 is synchronous — push it to a thread so we don't block the event loop.
    response = await run_in_threadpool(
        client.invoke_agent_runtime,
        agentRuntimeArn=AGENT_RUNTIME_ARN,
        runtimeSessionId=session_id,
        qualifier=AGENT_ENDPOINT_NAME,
        payload=payload,
    )
    body = await run_in_threadpool(response["response"].read)
    return json.loads(body)


@app.post(
    "/plan",
    responses={
        424: {"description": "The planner agent is temporarily unavailable (upstream HTTP error)."},
        502: {
            "description": "Unable to reach the planner agent or the AgentCore runtime returned an error."
        },
    },
)
async def plan(request: Request, body: PlanRequest):
    session_id = request.headers.get("x-session-id") or str(uuid.uuid4())

    logger = StructuredLogger(
        session_id=session_id,
        user_id=(body.user_context or {}).get("user_id", "unknown"),
        agent_name="planner-backend",
    )
    logger.log(
        "INFO",
        "Plan request received",
        mode="local" if LOCAL_MODE else "agentcore",
        situation_length=len(body.situation),
        step="plan_request",
    )

    try:
        if LOCAL_MODE:
            result = await _invoke_local(session_id, body.situation, body.user_context, logger)
        else:
            result = await _invoke_agentcore(session_id, body.situation, body.user_context, logger)
    except httpx.RequestError as e:
        logger.log(
            "ERROR", "Agent connection error", error_type=type(e).__name__, step="agent_call"
        )
        raise HTTPException(
            status_code=502, detail="Unable to reach the planner agent. Please try again."
        ) from e
    except httpx.HTTPStatusError as e:
        logger.log(
            "ERROR",
            "Agent HTTP error",
            status_code=e.response.status_code,
            error_body=e.response.text,
            step="agent_call",
        )
        raise HTTPException(
            status_code=424, detail="The planner agent is temporarily unavailable."
        ) from e
    except ClientError as e:
        logger.log(
            "ERROR",
            "AgentCore invocation error",
            error_code=e.response.get("Error", {}).get("Code"),
            error_message=e.response.get("Error", {}).get("Message"),
            step="agent_call",
        )
        raise HTTPException(
            status_code=502, detail="The AgentCore runtime returned an error."
        ) from e

    # The agent entrypoint returns InvocationResponse(output=...), so the
    # actual plan/agent_help payload sits under the "output" key.
    payload = unwrap_agent_output(result, logger)

    response = JSONResponse(content=payload)
    response.set_cookie(
        "sessionId",
        session_id,
        httponly=True,
        secure=True,
        samesite="lax",
    )
    return response
