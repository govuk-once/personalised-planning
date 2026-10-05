"""In-process agent driver: generate G plans per profile, capturing retrieval context.

The planner agent reads ``./system_prompt.md`` at module-load time via a
relative path, so cwd must be ``agent/app/`` when ``planner_agent`` is first
imported. This module saves and restores cwd around that import so the calling
harness is not surprised.
"""

import asyncio
import os
import sys
from pathlib import Path
from typing import Any

# ---------------------------------------------------------------------------
# Extend sys.path so the agent package tree is importable.
# Must happen before any import from agent/.
# ---------------------------------------------------------------------------
_REPO_ROOT = Path(__file__).resolve().parents[3]
_AGENT_DIR = _REPO_ROOT / "agent"
_AGENT_APP_DIR = _AGENT_DIR / "app"

for _p in (_AGENT_APP_DIR, _AGENT_DIR):
    _s = str(_p)
    if _s not in sys.path:
        sys.path.insert(0, _s)

# Also ensure the eval root (for run_app imports) is on the path
_EVAL_DIR = Path(__file__).resolve().parents[1]
if str(_EVAL_DIR) not in sys.path:
    sys.path.insert(0, str(_EVAL_DIR))

# ---------------------------------------------------------------------------
# Import agent code with cwd temporarily set to agent/app/ so that the
# module-level read_file_content("./system_prompt.md") resolves correctly.
# ---------------------------------------------------------------------------
_saved_cwd = os.getcwd()
os.chdir(_AGENT_APP_DIR)
try:
    from planner_agent import PlannerAgentRunner  # noqa: E402
    from shared.log_utils import StructuredLogger  # noqa: E402
finally:
    os.chdir(_saved_cwd)

from run_app import SITUATION, profile_context  # noqa: E402


def _build_prompt(situation: str, user_context: dict[str, Any] | None) -> str:
    """Vendored from planner_logic._build_prompt; avoids pulling in fastapi."""
    prompt = f"Situation: {situation}"
    if user_context:
        facts = [f"{k}: {v}" for k, v in user_context.items() if v is not None]
        if facts:
            prompt += "\n\nKnown facts about this person:\n" + "\n".join(facts)
    return prompt


def _make_logger(profile_id: str, verbose: bool = False) -> StructuredLogger:
    """Create a throwaway StructuredLogger for one profile run."""
    return StructuredLogger(
        session_id=f"eval-{profile_id}",
        user_id="eval-harness",
        agent_name="planner",
    )


async def _generate_once(profile: dict, logger: StructuredLogger) -> dict | None:
    """Run the planner once for a profile.

    Args:
        profile: A profile record from the profiles JSON.
        logger: A StructuredLogger instance for this run.

    Returns:
        Dict with ``plan``, ``retrieval_context`` (list of tool-result strings),
        and ``context`` (the user-context dict); or ``None`` if generation
        produced no plan.
    """
    context = profile_context(profile)
    prompt = _build_prompt(SITUATION, context)
    runner = PlannerAgentRunner(logger=logger)
    result = await runner.run(prompt, return_trace=True)
    plan = result.get("plan")
    if plan is None:
        return None
    return {
        "plan": plan,
        "retrieval_context": [
            t["tool_result"]
            for t in (result.get("trace") or [])
            if t.get("tool_result")
        ],
        "context": context,
    }


def generate_plans(
    profile: dict,
    G: int,
    logger: StructuredLogger | None = None,
) -> list[dict]:
    """Run the planner G times sequentially for one profile.

    Sequential rather than concurrent to avoid MCP stdio process conflicts and
    Bedrock throttling. Non-determinism across runs comes from the agent's own
    sampling temperature, which is what makes consistency scoring meaningful.

    Args:
        profile: A profile record from the profiles JSON.
        G: Number of generations to attempt.
        logger: Optional StructuredLogger; a throwaway one is created if absent.

    Returns:
        List of successful generation dicts (up to G entries; failed/None
        generations are dropped with a warning logged to stderr).
    """
    pid = profile.get("id", "unknown")
    log = logger or _make_logger(pid)
    results = []
    for i in range(G):
        log.log("INFO", f"Generation {i + 1}/{G}", profile_id=pid, step="generate")
        gen = asyncio.run(_generate_once(profile, log))
        if gen is not None:
            results.append(gen)
        else:
            print(f"  {pid}: generation {i + 1}/{G} returned no plan", file=sys.stderr)
    return results
