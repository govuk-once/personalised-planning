from enum import StrEnum

from pydantic import BaseModel, Field, model_validator


class Method(StrEnum):
    """
    Method through which a task can be completed.
    """

    IN_PERSON = "in-person"
    ONLINE = "online"
    PHONE = "phone"
    POST = "post"


class StepProgress(StrEnum):
    """
    User progress on the step.
    """

    NOT_STARTED = "Not started"
    IN_PROGRESS = "In progress"
    DONE = "Done"


class Task(BaseModel):
    """
    A single, detailed task used as part of a step in a personalised plan.
    """

    title: str = Field(description="The title of the task.")
    summary: str = Field(description="A short, 2-3 sentence summary suitable for the card view.")
    callout: str = Field(
        description="A sentence flagging an important requirement or deadline to user."
    )
    methods: list[Method] = Field(
        description="The methods by which this task can be completed,"
        "e.g. online, phone, post, in-person."
    )
    dept: str = Field(description="Name of the responsible government department.")
    completed: bool = Field(
        default=False, description="A flag indicating if user completed the task."
    )
    location: str | None = Field(
        default=None,
        description="Location where the task needs to be completed, e.g. 'Registry Office'. "
        "Required if 'in-person' is one of the methods, otherwise omit.",
    )
    deadline: str | None = Field(
        default=None,
        description="Timeline within which the task needs to be completed, omit if there are no deadlines.",
    )
    grant: str | None = Field(
        default=None,
        description="Known or standard benefit that the user should qualify for"
        "based on their circumstances, omit if not relevant",
    )
    gov_service_name: str = Field(
        description="Name of the relevant government service or programme"
    )
    gov_service_url: str = Field(
        description="URL link to the relevant government service or programme"
    )
    cost: float = Field(description="Cost of service, or 0.0 if there are no costs.")
    service_form_url: str | None = Field(
        default=None,
        description="URL link listed under onlineFormUrl in agentInteraction property of the service-graph,"
        "omit if not provided in the service-graph.",
    )
    service_form_label: str | None = Field(
        default=None, description="Plain English label for service_form_url."
    )
    what_to_expect: str = Field(
        description="An extended, 2-3 paragraph summary outlining essential information about the task."
    )
    requirements: list[str] = Field(
        description="List of requirements, such as documents or items, "
        "which user will need to complete the task."
    )


class Step(BaseModel):
    """
    A single, detailed step used in a personalised plan.
    """

    title: str = Field(description="The title of the step.")
    summary: str = Field(description="A short, 2-3 sentence summary suitable for the card view.")
    status: StepProgress
    tasks: list[Task] = Field(
        description="A list of specific tasks that need to be done as part of the step."
    )


class Plan(BaseModel):
    title: str = Field(description="Plan title.")
    summary: str = Field(description="A short, 2-3 sentence summary suitable for the card view.")
    steps: list[Step] = Field(description="A list of recommended steps for the user.")
    reasoning: str = Field(
        description="A high-level explanation of the strategy used to select this list of steps based on the user's circumstances."
    )


class AgentHelp(BaseModel):
    answer: str


class ResultPayload(BaseModel):
    model_config = {"extra": "forbid"}
    plan: Plan | None = None
    agent_help: AgentHelp | None = None

    @model_validator(mode="after")
    def at_least_one_present(self):
        if self.plan is None and self.agent_help is None:
            raise ValueError("ResultPayload must contain at least one of plan or agent_help")
        return self


class LLMResult(BaseModel):
    result: ResultPayload
