from datetime import UTC, datetime
from typing import Any

from fastapi import HTTPException
from planner_agent import PlannerAgentRunner
from shared.log_utils import StructuredLogger


async def run_planner(
    situation: str,
    auth_token: str | None = None,
    user_context: dict[str, Any] | None = None,
    logger: StructuredLogger | None = None,
) -> dict[str, Any]:
    """
    Core planning logic shared between local FastAPI and AgentCore entrypoints.
    """
    try:
        logger.log("INFO", "Planner agent invoked")

        if not situation:
            raise HTTPException(
                status_code=400,
                detail="'situation' is required in the input payload.",
            )

        if auth_token:
            logger.log("INFO", "Authorization token received", step="auth")
        else:
            logger.log("INFO", "No Authorization token provided", step="auth")

        logger.log(
            "INFO",
            "Processing request",
            situation=situation,
            step="process_request",
        )

        agent = PlannerAgentRunner(logger=logger, auth_token=auth_token)

        # Build the prompt — include user context facts if provided, as these
        # allow check_eligibility to return more precise verdicts
        prompt = _build_prompt(situation, user_context)
        logger.log("INFO", "Prompt sent to Agent", prompt=prompt, step="process_request")

        outputs = await agent.run(prompt)

        response = {
            "plan": outputs["plan"],
            "agent_help": outputs["agent_help"],
            "timestamp": datetime.now(UTC).isoformat(),
        }
        return response

    except Exception as e:
        logger.log("ERROR", "Planner processing failed", error=str(e))
        raise HTTPException(status_code=500, detail=f"Planner processing failed: {str(e)}") from e


def _build_prompt(situation: str, user_context: dict[str, Any] | None) -> str:
    """
    Build the agent prompt from the user's situation description and any
    structured facts that can sharpen eligibility checks.
    """
    prompt = f"Situation: {situation}"

    if user_context:
        facts = []
        # Surface any structured facts the caller has provided so check_eligibility
        # can run meaningful rules without needing to ask the user again
        for key, value in user_context.items():
            if value is not None:
                facts.append(f"{key}: {value}")
        if facts:
            prompt += "\n\nKnown facts about this person:\n" + "\n".join(facts)

    return prompt
