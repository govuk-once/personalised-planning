import json
import os
from datetime import UTC, datetime
from typing import Any

from chat_agent import ChatAgentRunner
from fastapi import HTTPException
from shared.log_utils import StructuredLogger

# Fallback cap: once the assistant has asked this many questions (turns), force
# the conversation to complete so the interview can't drag on indefinitely.
MAX_ASSISTANT_TURNS = int(os.getenv("CHAT_MAX_ASSISTANT_TURNS", "5"))
FALLBACK_COMPLETE_MESSAGE = "Thanks, that's all the info I need!"


def _message_text(message: dict[str, Any]) -> str:
    """Pull plain text out of a message whose content is a string or block list."""
    content = message.get("content", "")
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = [block.get("text", "") for block in content if isinstance(block, dict)]
        return "\n".join(p for p in parts if p)
    return str(content)


def _to_strands_history(messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """
    Convert caller messages ({role, content:str}) into the Strands content-block
    format Agent(messages=...) expects, so prior turns can be replayed statelessly.
    """
    history: list[dict[str, Any]] = []
    for message in messages:
        role = message.get("role", "user")
        text = _message_text(message)
        if not text:
            continue
        history.append({"role": role, "content": [{"text": text}]})
    return history


def _context_note(user_context: dict[str, Any] | None) -> str:
    """Without `today` the agent dates relative times from its training cutoff."""
    context = dict(user_context or {})
    today = context.pop("today", None)
    life_event_ids = context.pop("life_event_ids", None)
    outstanding = context.pop("outstanding", None)

    parts = []
    if today:
        parts.append(f"Today's date is {today}. Resolve every relative date against it.")
    if life_event_ids:
        ids_str = ", ".join(life_event_ids)
        parts.append(
            f"Life events already confirmed from a prior turn: {ids_str}. "
            "Do NOT call list_life_events again unless the user describes a new situation "
            "not covered by these IDs."
        )
    if context:
        parts.append(
            "Facts you established earlier in this conversation. Treat them as already "
            f"answered and do not ask about them again:\n{json.dumps(context, indent=2)}"
        )
    if outstanding:
        items = "\n".join(f"- {q}" for q in outstanding)
        parts.append(
            "Questions still outstanding from the previous turn. Remove any the user just "
            "answered (directly or by implication), then ask the next one or two from this "
            "list. Only call get_required_information again if this list is empty or you "
            f"need to refresh it:\n{items}"
        )
    return "\n\n".join(parts)


async def run_chat(
    messages: list[dict[str, Any]],
    user_context: dict[str, Any] | None = None,
    logger: StructuredLogger | None = None,
) -> dict[str, Any]:
    """
    Core conversational logic shared between local FastAPI and AgentCore
    entrypoints. The caller holds the whole message history and replays it each
    turn — nothing is stored server-side.
    """
    try:
        if logger:
            logger.log("INFO", "Chat agent invoked")

        if not messages:
            raise HTTPException(
                status_code=400,
                detail="'messages' is required and must be non-empty in the input payload.",
            )

        # The transcript must end with the user's newest message — that becomes
        # the prompt; everything before it is replayed as prior context.
        if messages[-1].get("role") != "user":
            raise HTTPException(
                status_code=400,
                detail="The last message must be from the user.",
            )

        prompt = _message_text(messages[-1])
        if not prompt:
            raise HTTPException(
                status_code=400, detail="The last user message has no text content."
            )

        history = _to_strands_history(messages[:-1])

        if logger:
            logger.log(
                "INFO",
                "Processing chat turn",
                turns=len(messages),
                step="process_request",
            )

        agent = ChatAgentRunner(logger=logger)
        turn = await agent.run(prompt, history=history, context=_context_note(user_context))

        if turn is None:
            raise HTTPException(
                status_code=502,
                detail="The chat agent did not return a valid response.",
            )

        turn["timestamp"] = datetime.now(UTC).isoformat()

        # Fallback cap: once the assistant has already asked MAX_ASSISTANT_TURNS
        # questions, force completion so the interview can't drag on. Counting
        # assistant messages in the replayed transcript is the stateless way to
        # know how many have been asked.
        # When the cap fires we roll collected_facts back to the baseline that
        # was passed *into* this turn — the agent may have speculatively filled
        # fields the user was never asked about, and those shouldn't reach the
        # planner.
        assistant_turns = sum(1 for m in messages if m.get("role") == "assistant")
        if assistant_turns >= MAX_ASSISTANT_TURNS:
            if logger:
                logger.log(
                    "INFO",
                    "Question cap reached — forcing completion",
                    assistant_turns=assistant_turns,
                    cap=MAX_ASSISTANT_TURNS,
                    step="question_cap",
                )
            baseline_facts = dict(user_context or {})
            for key in ("today", "life_event_ids", "outstanding"):
                baseline_facts.pop(key, None)
            turn["collected_facts"] = baseline_facts
            turn["complete"] = True
            turn["message"] = FALLBACK_COMPLETE_MESSAGE

        # Once the conversation is complete, distil the whole conversation into a
        # one-sentence `situation` the frontend can hand straight to /plan.
        if turn.get("complete"):
            transcript = "\n".join(
                f"{message.get('role', 'user')}: {_message_text(message)}"
                for message in messages
                if _message_text(message)
            )
            turn["situation"] = await agent.summarise_situation(transcript)

        return turn

    except HTTPException:
        raise
    except Exception as e:
        if logger:
            logger.log("ERROR", "Chat processing failed", error=str(e))
        raise HTTPException(status_code=500, detail=f"Chat processing failed: {str(e)}") from e
