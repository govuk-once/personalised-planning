from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator


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
        description="The next thing to say to the user — usually one question, "
        "or a short wrap-up once all needed information has been gathered."
    )
    life_event_ids: list[str] = Field(
        default_factory=list,
        description="Life event IDs identified from the conversation so far "
        "(from list_life_events), e.g. ['baby', 'job-loss'].",
    )
    collected_facts: dict[str, Any] = Field(
        description="Facts gathered so far, keyed by UserContext field name. "
    )
    outstanding: list[str] = Field(
        description="Information still needed before planning, from get_required_information. "
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
    quick_replies: list[str] = Field(
        default_factory=list,
        description="Answers the person can tap instead of typing, for the one question in "
        "`message`: 2 to 8, counting any 'Not sure', each a few words, mutually exclusive. "
        "[] for an open question, two questions at once, any amount, age or other number "
        "(no bands either), and when `complete` is true. "
        "A tap comes back word for word as the person's next message.",
    )
    answer_format: Literal["text", "date"] = Field(
        default="text",
        description="'date' when `message` asks for one particular date, such as a birth, "
        "a death or a start date: the page then offers a date picker. Otherwise 'text'.",
    )

    # Anything but a list of strings means none: a turn is never retried over its options.
    @field_validator("quick_replies", mode="before")
    @classmethod
    def _labels_or_none(cls, value: Any) -> list[str]:
        if not isinstance(value, list):
            return []

        for label in value:
            if not isinstance(label, str):
                return []

        return value

    @field_validator("answer_format", mode="before")
    @classmethod
    def _text_unless_date(cls, value: Any) -> str:
        if value == "date":
            return "date"

        return "text"
