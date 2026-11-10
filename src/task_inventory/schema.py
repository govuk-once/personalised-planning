"""
Task Extraction V3: Schema and Data Models

Defines all Pydantic models and vocabulary types used across the pipeline.
Normalisation (synonym repair, URL fixing, policy mapping) runs here before
Pydantic validation so that minor LLM output variations don't cause rejections.

Key models:
- TaskBody       Base model with all LLM-written fields (policy, title, actor, window, etc.)
- Draft          One task found in a single section; output of stage 3.  Has draft_id + source.
- TaskRecord     Final merged task; output of stage 4.  Has id, sources, sensitivity, etc.
- SectionDrafts  Tool-use wrapper returned by the stage-3 LLM call.
- ClusterResult  Tool-use wrapper returned by the stage-4b clustering call.

Key vocabulary types (all Literal):
- Actor, Method, Anchor, Unit, Phase, Journey, Policy, OtherParty, Label

Key functions:
- normalise(data, warnings)   Recursively repairs LLM output before validation.
- normalise_value(field, val) Applies synonym table for a single field.
- convert_qualifying_week(tb) Rewrites qualifying_week anchors to due_week with offset.

No external file or network dependencies; pure in-memory model definitions.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field, model_validator

# ============================================================================
# Vocabularies
# ============================================================================

Actor = Literal["birth_parent", "partner", "either_parent", "both_parents"]

Method = Literal[
    "online", "phone", "post", "in_person", "via_employer", "via_registrar", "off_platform"
]

Anchor = Literal[
    "pregnancy_week",
    "due_week",
    "qualifying_week",
    "birth",
    "registration",
    "smp_start",
    "leave_start",
    "return_date",
    "decision_date",
    "application_date",
    "benefit_claim_start",
    "pregnancy_loss",
    "death",
]

Unit = Literal["hour", "day", "week", "month", "year"]

Phase = Literal["pregnancy", "birth", "after_birth"]

Journey = Literal["typical", "neonatal", "loss", "abroad", "surrogacy"]

OtherParty = Literal["employer", "registrar", "hmrc", "dwp", "nhs", "council", "court"]

Label = Literal["action", "deadline", "condition", "expectation", "guidance"]

Policy = Literal[
    "Statutory Maternity Pay",
    "Maternity Leave",
    "Maternity Allowance",
    "Paternity Leave and Pay",
    "Shared Parental Leave and Pay",
    "Neonatal Care Leave and Pay",
    "Bereaved Partner's Paternity Leave",
    "Parental Leave",
    "Antenatal Rights",
    "Employment Rights",
    "Flexible Working",
    "Birth Registration",
    "Stillbirth Registration",
    "Certificates",
    "Child Benefit",
    "Sure Start Maternity Grant",
    "Healthy Start",
    "Universal Credit",
    "Childcare",
    "Baby Loss Certificate",
    "Other",
]


# ============================================================================
# Normalisation
# ============================================================================

SYNONYMS: dict[str, dict[str, str]] = {
    "method": {
        "in-person": "in_person",
        "postal": "post",
        "paper_form": "post",
        "employer": "via_employer",
    },
    "anchor": {
        "start_of_pregnancy": "pregnancy_week",
        "expected_week_of_childbirth": "due_week",
        "qualifying_week": "due_week",  # Converted with offset adjustment
    },
    "unit": {
        "days": "day",
        "weeks": "week",
        "months": "month",
        "hours": "hour",
        "years": "year",
    },
}

# Verb list for title validation (multi-word verbs should come before their single-word parts)
VERBS = [
    "Give notice",
    "Get help",
    "Opt out",
    "Work out",  # Multi-word first
    "Check",
    "Tell",
    "Give",
    "Claim",
    "Apply",
    "Register",
    "Order",
    "Plan",
    "Report",
    "Take",
    "Challenge",
    "Send",
    "Request",
    "Transfer",
    "Choose",
    "Arrange",
    "Contact",
    "Attend",
    "Restart",
    "Complain",
    "Notify",
    "Book",
    "Query",
    "Use",
    "Meet",
    "Manage",
    "Follow",
]


def normalise_value(field: str, value: str) -> str:
    """Normalise a single vocabulary value using synonym table"""
    if field in SYNONYMS and value in SYNONYMS[field]:
        return SYNONYMS[field][value]
    return value


def convert_qualifying_week(task_body) -> None:
    """
    Convert qualifying_week anchors to due_week with offset adjustment.

    The qualifying week is the 15th week before the due week.
    qualifying_week +0 → due_week -15
    qualifying_week +3 → due_week -12

    Applied after validation so checks see the original text.
    Modifies task_body in place.
    """

    def convert_window_end(end: WindowEnd | None) -> None:
        if end and end.anchor == "qualifying_week" and end.unit == "week":
            end.note = f"converted from qualifying_week{end.offset:+d}"
            end.anchor = "due_week"
            end.offset = end.offset - 15

    if task_body.window:
        convert_window_end(task_body.window.opens)
        convert_window_end(task_body.window.closes)

    for sub_task in task_body.sub_tasks:
        if sub_task.window:
            convert_window_end(sub_task.window.opens)
            convert_window_end(sub_task.window.closes)


def normalise(data: dict, warnings: list[str] | None = None) -> dict:
    """
    Recursively normalise vocabulary fields before validation.

    Handles:
    - method, anchor, unit synonyms
    - nested structures (window, duration, sub_tasks, etc.)
    - repairs: URLs, titles, policies
    - qualifying_week → due_week conversion

    Args:
        data: Input dict from LLM
        warnings: Optional list to collect warnings (e.g., TITLE_TRUNCATED)

    Returns:
        Normalised dict
    """
    if warnings is None:
        warnings = []

    if not isinstance(data, dict):
        return data

    result = {}
    for key, value in data.items():
        # Fix URLs
        if key == "url" and isinstance(value, str):
            if value.startswith("mailto:"):
                result[key] = None
                warnings.append("URL_MAILTO")
            elif value.startswith("/"):
                result[key] = f"https://www.gov.uk{value}"
            else:
                result[key] = value

        # Truncate long titles
        elif key == "title" and isinstance(value, str) and len(value) > 70:
            # Cut at last word boundary before 70
            truncated = value[:70].rsplit(" ", 1)[0]
            result[key] = truncated
            warnings.append(f"TITLE_TRUNCATED (original: {value})")

        # Map unknown policies to "Other"
        elif key == "policy" and isinstance(value, str):
            # Check if value is in Policy literal
            from typing import get_args

            valid_policies = get_args(Policy)
            if value not in valid_policies:
                result["policy_raw"] = value  # Store original
                result[key] = "Other"
                warnings.append(f"POLICY_UNMAPPED ({value} → Other)")
            else:
                result[key] = value

        # Normalise vocabulary fields
        elif key == "method" and isinstance(value, str):
            result[key] = normalise_value("method", value)
        elif key == "anchor" and isinstance(value, str):
            result[key] = normalise_value("anchor", value)
        elif key == "unit" and isinstance(value, str):
            result[key] = normalise_value("unit", value)

        # Recursively handle nested dicts
        elif isinstance(value, dict):
            result[key] = normalise(value, warnings)

        # Handle lists of dicts
        elif isinstance(value, list):
            result[key] = [
                normalise(item, warnings) if isinstance(item, dict) else item for item in value
            ]
        else:
            result[key] = value

    return result


# ============================================================================
# Models
# ============================================================================


class Cited(BaseModel):
    """Text with evidence"""

    text: str
    evidence: list[str] = Field(min_length=1, description="Sentence IDs")


class WindowEnd(BaseModel):
    """One end of a timing window"""

    anchor: Anchor
    offset: int = Field(description="Signed: negative = before, positive = after")
    unit: Unit
    evidence: list[str] = Field(min_length=1)
    note: str | None = Field(
        default=None, description="Conversion notes (e.g., qualifying_week→due_week)"
    )


class Window(BaseModel):
    """Timing window with independent opens and closes"""

    opens: WindowEnd | None = None
    closes: WindowEnd | None = None


class Duration(BaseModel):
    """Leave length or protection period (not a deadline)"""

    value: int
    unit: Unit
    evidence: list[str] = Field(min_length=1)


class Expectation(Cited):
    """What another party must do"""

    party: OtherParty


class SubTask(Cited):
    """Ordered step within a task"""

    window: Window | None = None


class Variant(BaseModel):
    """Nation-specific variant"""

    nation: Literal["england", "wales", "scotland", "northern_ireland"]
    url: str | None = None
    title: str | None = None
    evidence: list[str] = Field(default_factory=list)


class Source(BaseModel):
    """Where a draft or task came from"""

    base_path: str
    section_path: str  # e.g. "How to claim > What you'll need"
    draft_id: str


class TaskBody(BaseModel):
    """
    Fields the LLM writes. IDs and sources are set by code.

    This is the base for both Draft and TaskRecord.
    """

    policy: Policy
    title: str = Field(max_length=70, description="Verb-first title")
    actor: Actor
    method: Method
    url: str | None = None
    window: Window | None = None
    duration: Duration | None = None
    requires: list[Cited] = Field(default_factory=list)
    expectations: list[Expectation] = Field(default_factory=list)
    sub_tasks: list[SubTask] = Field(default_factory=list)
    guidance: list[Cited] = Field(default_factory=list)  # V2 used string; list allows merging
    phase: Phase
    journeys: list[Journey] = Field(min_length=1)
    evidence: list[str] = Field(min_length=1, description="All sentence IDs cited")


class Draft(TaskBody):
    """
    Output from stage 3 (section drafts).

    One draft per task found in a section. May be merged later.
    """

    draft_id: str
    source: Source
    status: Literal["ok", "rejected"] = "ok"
    errors: list[str] = Field(default_factory=list)


class TaskRecord(TaskBody):
    """
    Final task record after clustering and merging.

    May be composed from multiple drafts.
    """

    id: str = Field(description="Kebab-case ID: slug(policy)--slug(canonical title)")
    sensitivity: Literal["normal", "loss"] = "normal"
    alternative_to: list[str] = Field(
        default_factory=list, description="Task IDs this is alternative to"
    )
    variants: list[Variant] = Field(default_factory=list)
    sources: list[Source] = Field(min_length=1, description="Every draft merged into this task")
    status: Literal["ok", "needs_review"] = "ok"

    @model_validator(mode="after")
    def set_sensitivity(self):
        """Automatically set sensitivity=loss if loss in journeys"""
        if "loss" in self.journeys:
            self.sensitivity = "loss"
        return self


# ============================================================================
# LLM output wrappers
# ============================================================================


class SectionDrafts(BaseModel):
    """Output from stage 3: section draft call"""

    drafts: list[TaskBody] = Field(
        description="0-n tasks, as many as the section genuinely contains"
    )


class Member(BaseModel):
    """One draft's membership in a cluster"""

    draft_id: str
    role: Literal["primary", "same", "sub_task"]
    parent_draft_id: str | None = Field(default=None, description="Required when role=sub_task")


class Cluster(BaseModel):
    """Group of related drafts"""

    key: str = Field(description="Short label used within this clustering response")
    canonical_title: str = Field(max_length=70)
    members: list[Member]


class ClusterResult(BaseModel):
    """Output from stage 4b: clustering call"""

    clusters: list[Cluster]
    alternatives: list[tuple[str, str]] = Field(
        default_factory=list,
        description="Pairs of cluster keys that are alternatives (e.g. online/postal)",
    )
