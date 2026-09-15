from typing import Any

from pydantic import BaseModel, Field


class ConversationTurn(BaseModel):
    """
    The agent's output for a single conversational turn.

    The agent stores nothing server-side — the caller holds the whole message
    history and passes it back each turn, so every field here is re-derived from
    the transcript on each invocation. `collected_facts` uses the same
    UserContext field vocabulary as the service-graph tools, so once `complete`
    is true the caller can pass it straight to /plan as `user_context`.
    """

    model_config = {"extra": "forbid"}

    message: str = Field(
        description="The next thing to say to the user — usually one or two questions, "
        "or a short wrap-up once all needed information has been gathered."
    )
    life_event_ids: list[str] = Field(
        default_factory=list,
        description="Life event IDs identified from the conversation so far "
        "(from list_life_events), e.g. ['baby', 'job-loss'].",
    )
    collected_facts: dict[str, Any] = Field(
        default_factory=dict,
        description="Facts gathered so far, keyed by UserContext field name "
        "(e.g. {'age': 34, 'has_children': true}). Re-derived from the whole transcript.",
    )
    outstanding: list[str] = Field(
        default_factory=list,
        description="Information still needed before planning, from get_required_information.",
    )
    complete: bool = Field(
        default=False,
        description="True once nothing is outstanding — the caller then hands "
        "collected_facts to the /plan endpoint.",
    )
    situation: str | None = Field(
        default=None,
        description="One-sentence summary of what the user wants help with, for "
        "the /plan endpoint's `situation` input. Populated only once `complete` "
        "is true; it is set after the interview turn by a separate summarisation "
        "call, not produced by the interviewer, so leave it null.",
    )
