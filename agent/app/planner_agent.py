import os
import time

from botocore.config import Config as BotocoreConfig
from dotenv import load_dotenv
from mcp import StdioServerParameters, stdio_client
from mcp.client.streamable_http import streamablehttp_client
from shared.log_utils import StructuredLogger
from shared.utils import read_file_content
from strands import Agent
from strands.hooks import (
    AfterInvocationEvent,
    AfterToolCallEvent,
    BeforeInvocationEvent,
    BeforeToolCallEvent,
    HookProvider,
    HookRegistry,
)
from strands.models import BedrockModel
from strands.tools.mcp import MCPClient
from strands.types.exceptions import StructuredOutputException
from structured_outputs import ResultPayload

load_dotenv()

MODEL_ID = os.getenv("ANTHROPIC_MODEL", "eu.anthropic.claude-sonnet-5")
BEDROCK_REGION = os.getenv("AWS_REGION", "eu-west-2")

MCP_MODE = os.getenv("MCP_MODE", "remote")

if MCP_MODE == "local":
    GRAPH_MCP_URL = os.getenv("GRAPH_SERVER_PATH")
else:
    GRAPH_MCP_URL = os.getenv("GRAPH_GATEWAY_URL")

SYSTEM_PROMPT = read_file_content("./system_prompt.md")


class PlannerObservabilityHooks(HookProvider):
    """
    Strands fires typed hook events instead of
    streaming raw message blocks, so tool-use / tool-result / timing logging
    becomes a handful of callbacks rather than an if/elif ladder.
    """

    def __init__(self, logger: StructuredLogger):
        self.logger = logger
        self._invocation_start: float | None = None
        self._last_tool_result_at: float | None = None

    def register_hooks(self, registry: HookRegistry, **kwargs) -> None:
        registry.add_callback(BeforeInvocationEvent, self._on_invocation_start)
        registry.add_callback(AfterInvocationEvent, self._on_invocation_end)
        registry.add_callback(BeforeToolCallEvent, self._on_tool_start)
        registry.add_callback(AfterToolCallEvent, self._on_tool_end)

    def _on_invocation_start(self, event: BeforeInvocationEvent) -> None:
        self._invocation_start = time.perf_counter()
        self.logger.log("INFO", "Agent invocation started", step="invocation_start")

    def _on_invocation_end(self, event: AfterInvocationEvent) -> None:
        elapsed = (
            round(time.perf_counter() - self._invocation_start, 2)
            if self._invocation_start is not None
            else None
        )
        self.logger.log(
            "INFO", "Agent invocation complete", elapsed_s=elapsed, step="invocation_end"
        )

    def _on_tool_start(self, event: BeforeToolCallEvent) -> None:
        tool_use = event.tool_use
        self.logger.log(
            "INFO",
            f"TOOL USE: {tool_use.get('name')}",
            tool_use_id=tool_use.get("toolUseId"),
            tool_name=tool_use.get("name"),
            input=str(tool_use.get("input"))[:200],
            step="tool_use",
        )

    def _on_tool_end(self, event: AfterToolCallEvent) -> None:
        elapsed_since_last = (
            round(time.perf_counter() - self._last_tool_result_at, 2)
            if self._last_tool_result_at is not None
            else None
        )
        self._last_tool_result_at = time.perf_counter()
        self.logger.log(
            "INFO",
            "Tool result received",
            tool_use_id=event.tool_use.get("toolUseId"),
            elapsed_since_last_tool_result_s=elapsed_since_last,
            step="tool_result",
        )


def _build_mcp_client_service_graph() -> MCPClient:
    """
    Stdio for local dev against the TS graph-server directly, streamable HTTP for the deployed AgentCore
    Gateway URL.
    """
    if GRAPH_MCP_URL and GRAPH_MCP_URL.startswith("http"):
        return MCPClient(lambda: streamablehttp_client(GRAPH_MCP_URL))

    return MCPClient(
        lambda: stdio_client(
            StdioServerParameters(
                command="npx",
                args=["tsx", f"{GRAPH_MCP_URL}/src/graph-server.ts"],
                env={"PATH": os.environ.get("PATH", "")},
            )
        )
    )


class PlannerAgentRunner:
    """
    Runs the personalised planning agent using the UK government services
    graph MCP server to generate a personalised service journey plan.
    """

    def __init__(self, auth_token: str = None, logger: StructuredLogger | None = None):
        self.logger = logger
        self.auth_token = auth_token

        if logger:
            logger.log("INFO", f"Utilising Model: {MODEL_ID}")
            logger.log(
                "INFO",
                f"Configuring MCP ({MCP_MODE})",
                mcp_target=GRAPH_MCP_URL,
                step="mcp_config",
            )

    async def run(self, prompt: str) -> dict:
        boto_config = BotocoreConfig(read_timeout=180)
        model = BedrockModel(
            model_id=MODEL_ID,
            region_name=BEDROCK_REGION,
            boto_client_config=boto_config,
            max_tokens=32000,
        )
        mcp_client = _build_mcp_client_service_graph()

        # Managed integration — passing the MCPClient into tools=[] handles
        # connection lifecycle automatically, no `with mcp_client:` needed.
        agent = Agent(
            model=model,
            tools=[mcp_client],
            system_prompt=SYSTEM_PROMPT,
            hooks=[PlannerObservabilityHooks(self.logger)],
        )

        self.logger.log("INFO", "Starting Planner Agent", model=MODEL_ID, prompt_length=len(prompt))

        try:
            # structured_output_model=ResultPayload asks Strands to generate a
            # tool directly from ResultPayload's schema and force the model to call it
            result = await agent.invoke_async(prompt, structured_output_model=ResultPayload)
        except StructuredOutputException as e:
            self.logger.log(
                "WARNING",
                "Structured output validation failed after retries",
                error=str(e),
                step="structured_output_failed",
            )
            return {"plan": None, "agent_help": None}
        except Exception as e:
            self.logger.log(
                "ERROR",
                "Error during agent execution",
                error=str(e),
                error_type=type(e).__name__,
                step="agent_execution",
            )
            raise

        parsed: ResultPayload | None = getattr(result, "structured_output", None)

        if parsed is None:
            self.logger.log(
                "WARNING", "No structured output returned by agent", step="completion_check"
            )
            return {"plan": None, "agent_help": None}

        missing = [
            key
            for key, value in (("plan", parsed.plan), ("agent_help", parsed.agent_help))
            if value is None
        ]
        if missing:
            self.logger.log(
                "WARNING",
                "Agent completed with missing structured outputs",
                missing=missing,
                step="completion_check",
            )

        self.logger.log(
            "DEBUG",
            "Structured output received",
            raw_payload=parsed.model_dump(),
            step="structured_output_received",
        )

        return {
            "plan": parsed.plan.model_dump() if parsed.plan else None,
            "agent_help": parsed.agent_help.model_dump() if parsed.agent_help else None,
        }
