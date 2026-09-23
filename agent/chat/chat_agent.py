import asyncio
import json
import os
import time

import boto3
from dotenv import load_dotenv
from mcp import StdioServerParameters, stdio_client
from mcp.client.streamable_http import streamablehttp_client
from shared.log_utils import StructuredLogger
from shared.utils import read_file_content
from strands import Agent, tool
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
from structured_outputs import ConversationTurn

load_dotenv()

MODEL_ID = os.getenv("ANTHROPIC_MODEL", "eu.anthropic.claude-sonnet-5")
BEDROCK_REGION = os.getenv("AWS_REGION", "eu-west-2")

MCP_MODE = os.getenv("MCP_MODE", "remote")

if MCP_MODE == "local":
    GRAPH_MCP_URL = os.getenv("GRAPH_SERVER_PATH")
else:
    GRAPH_MCP_URL = os.getenv("GRAPH_GATEWAY_URL")

# "graph" (default)  — live service-graph MCP, same as the planner.
# "static_questions" — fixed question set from ./questions.json; no MCP server needed.
QUESTION_SOURCE = os.getenv("QUESTION_SOURCE", "graph").lower()

if QUESTION_SOURCE == "static_questions":
    SYSTEM_PROMPT = read_file_content("./system_prompt_static_questions.md")
else:
    SYSTEM_PROMPT = read_file_content("./system_prompt.md")

# Loaded at import in both modes — small, and avoids a conditional read.
QUESTIONS = json.loads(read_file_content("./questions.json"))["questions"]
# One-shot summarisation prompt, used once the conversation is complete to distil
# the whole conversation into a single sentence for the planner's `situation`.
SUMMARY_SYSTEM_PROMPT = read_file_content("./summary_prompt.md")

# boto3 clients are thread-safe and cheap to reuse across invocations.
_bedrock_runtime_client = None


def _get_bedrock_runtime_client():
    global _bedrock_runtime_client
    if _bedrock_runtime_client is None:
        _bedrock_runtime_client = boto3.client("bedrock-runtime", region_name=BEDROCK_REGION)
    return _bedrock_runtime_client


class ChatObservabilityHooks(HookProvider):
    """
    Strands fires typed hook events instead of streaming raw message blocks, so
    tool-use / tool-result / timing logging becomes a handful of callbacks
    rather than an if/elif ladder.
    """

    def __init__(self, logger):
        self.logger = logger
        self._invocation_start = None
        self._last_tool_result_at = None
        self.last_required_info_summary: dict | None = None

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
            input=str(tool_use.get("input")),
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
            status=event.result.get("status"),
            result=str(event.result.get("content"))[
                :2000
            ],  # untruncated enough to see known_facts/outstanding fully — bump/remove the cap for this diagnostic pass
            elapsed_since_last_tool_result_s=elapsed_since_last,
            step="tool_result",
        )
        if event.tool_use.get("name", "").endswith("get_required_information"):
            try:
                text = event.result.get("content", [{}])[0].get("text", "")
                self.last_required_info_summary = json.loads(text).get("summary")
            except Exception:
                pass


def _build_mcp_client_service_graph() -> MCPClient:
    """
    Stdio for local dev against the TS graph-server directly, streamable HTTP for
    the deployed AgentCore Gateway URL. Identical wiring to the planner — both
    agents talk to the same service-graph MCP server.
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


@tool
def ask_static_questions(known_facts: dict | None = None) -> dict:
    """Return the questions still outstanding for the user's plan.

    Filters the static question set against facts already gathered. When
    `questions` is empty every required fact has been collected.

    Args:
        known_facts: Facts established so far, keyed by UserContext field name
            (e.g. {"age": 34, "nation": "England"}).
    """
    known = known_facts or {}
    outstanding = [q for q in QUESTIONS if q["field"] not in known]
    return {
        "summary": {
            "totalQuestions": len(QUESTIONS),
            "answered": len(QUESTIONS) - len(outstanding),
            "outstanding": len(outstanding),
        },
        "questions": outstanding,
    }


class ChatAgentRunner:
    """
    Runs the conversational information-gathering agent. It interviews the user
    to work out which government services apply and what facts those services
    need, then asks questions until nothing is outstanding.

    Stateless: the caller holds the whole message history and replays it every
    turn via Strands' `Agent(messages=...)`, so the agent re-derives everything
    from the transcript each invocation.
    """

    def __init__(self, logger: StructuredLogger | None = None):
        self.logger = logger

        if logger:
            logger.log("INFO", f"Utilising Model: {MODEL_ID}")
            if QUESTION_SOURCE == "static_questions":
                logger.log(
                    "INFO",
                    "Question source: static_questions",
                    question_count=len(QUESTIONS),
                    step="questions_config",
                )
            else:
                logger.log(
                    "INFO",
                    f"Question source: graph (MCP {MCP_MODE})",
                    mcp_target=GRAPH_MCP_URL,
                    step="questions_config",
                )

    async def run(self, prompt: str, history: list[dict] | None = None, context: str = "") -> dict:
        model = BedrockModel(model_id=MODEL_ID, region_name=BEDROCK_REGION)

        # static_questions: single in-process tool over the fixed question set.
        # graph (default): live service-graph MCP (list_life_events + get_required_information).
        if QUESTION_SOURCE == "static_questions":
            tools = [ask_static_questions]
        else:
            tools = [_build_mcp_client_service_graph()]

        # Seed prior turns so the invocation is stateless — the caller-held
        # transcript is the single source of truth.
        hooks = [ChatObservabilityHooks(self.logger)] if self.logger else []
        agent = Agent(
            model=model,
            tools=[tools],
            system_prompt=f"{SYSTEM_PROMPT}\n\n### Known context\n{context}"
            if context
            else SYSTEM_PROMPT,
            messages=history or [],
            hooks=hooks,
        )

        if self.logger:
            self.logger.log(
                "INFO", "Starting Chat Agent", model=MODEL_ID, prompt_length=len(prompt)
            )

        try:
            result = await agent.invoke_async(prompt, structured_output_model=ConversationTurn)
        except StructuredOutputException as e:
            self.logger.log(
                "WARNING",
                "Structured output validation failed after retries",
                error=str(e),
                step="structured_output_failed",
            )
            return None
        except Exception as e:
            self.logger.log(
                "ERROR",
                "Error during agent execution",
                error=str(e),
                error_type=type(e).__name__,
                step="agent_execution",
            )
            raise

        parsed: ConversationTurn | None = getattr(result, "structured_output", None)

        if parsed is None:
            self.logger.log(
                "WARNING", "No structured output returned by agent", step="completion_check"
            )
            return None

        self.logger.log(
            "DEBUG",
            "Structured output received",
            raw_payload=parsed.model_dump(),
            step="structured_output_received",
        )

        return parsed.model_dump()

    async def summarise_situation(self, transcript: str) -> str:
        """
        Distil the whole conversation into a single sentence describing what the
        user wants help with, suitable for the planner's `situation` input.

        A one-shot Bedrock `converse` call rather than a full Strands Agent —
        there are no tools or multi-turn state to manage here. A summarisation
        failure must never break an otherwise-complete turn, so on any error we
        log and return an empty string.
        """
        client = _get_bedrock_runtime_client()

        def _invoke() -> str:
            # Wrap the transcript in XML tags so the model treats it as data to
            # summarise rather than a conversation to continue, then restate the
            # instruction after the closing tag — a trailing directive is harder
            # to override than a system-only prompt.
            user_text = (
                "<transcript>\n" + transcript + "\n</transcript>\n\n"
                "Summarise the above transcript in exactly one plain-English sentence "
                "from the person's perspective. Respond with only that sentence — "
                "no preamble, no quotation marks, no bullet points."
            )
            resp = client.converse(
                modelId=MODEL_ID,
                system=[{"text": SUMMARY_SYSTEM_PROMPT}],
                messages=[{"role": "user", "content": [{"text": user_text}]}],
                inferenceConfig={"maxTokens": 524},
            )
            return resp["output"]["message"]["content"][0]["text"].strip()

        try:
            # converse() is a blocking boto3 call — keep it off the event loop.
            situation = await asyncio.to_thread(_invoke)
        except Exception as e:
            if self.logger:
                self.logger.log(
                    "ERROR",
                    "Situation summarisation failed",
                    error=str(e),
                    error_type=type(e).__name__,
                    step="summarise_situation",
                )
            return ""

        if self.logger:
            self.logger.log(
                "INFO",
                "Situation summary generated",
                situation=situation,
                step="summarise_situation",
            )
        return situation
