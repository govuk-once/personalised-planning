"""
Stage 3: Section Drafts

Makes one LLM call per section that has at least one keep=Y candidate sentence,
asking the model to produce 0-n structured Draft objects from the section text.
Each draft is validated individually (schema + evidence + journey checks); a
failed draft does not discard the rest of the section.  One automatic retry is
made per section if any draft is invalid, with the errors fed back.

Key functions:
- run_section_drafts(sentences_path, candidates_path, output_dir, pages, model_id, region)
      Top-level entry point called by scripts/task_inventory/run_pipeline.py.
- process_section(base_path, content_id, section_path, ...)
      Builds the prompt, calls the LLM (up to twice), validates each draft, returns
      (ok_drafts, rejected_records).
- validate_one(raw, section_evidence_ids, evidence_texts, out_of_scope_ids)
      Runs normalise() + Pydantic + check_evidence_and_journeys + check_draft on one
      raw LLM dict; returns (TaskBody | None, errors).
- build_prompt(base_path, section_path, parent_heading, sentences, flagged_ids, ...)
      Renders the prompt template from prompts/section_drafts.md.

Run via:
    python scripts/task_inventory/run_pipeline.py --stage drafts

Assumptions:
- Prompt template must exist at  prompts/section_drafts.md  (relative to CWD).
- Optional scope rules file at   data/scope.yaml  (exclude_sections / exclude_sentence_patterns).
- Input:  data/sentences_extracted.csv  and  data/candidates.csv.
- Output written to  data/runs/latest/  (or the directory passed via output_dir):
    drafts.jsonl           — validated Draft objects, one per line.
    drafts_rejected.jsonl  — rejected records with reason and raw LLM output.
    stage3_summary.json    — counts and list of sections with rejections.
- LLM calls are cached under  data/cache/drafts/<hash>.json;  delete to force re-run.
- Requires AWS Bedrock credentials; model defaults to env ANTHROPIC_MODEL or
  eu.anthropic.claude-sonnet-5.
"""

import hashlib
import json
from collections import defaultdict
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field, ValidationError

from src.task_inventory.checks import check_draft as check_draft_content
from src.task_inventory.llm import call_structured, make_cache_key
from src.task_inventory.schema import Draft, SectionDrafts, Source, TaskBody

try:  # normalise() repairs synonyms, long titles, unknown policies, relative URLs
    from src.task_inventory.schema import normalise as _normalise
except ImportError:  # pragma: no cover
    _normalise = None


SPECIAL_JOURNEYS = {"neonatal", "loss", "abroad", "surrogacy"}


class LooseSectionDrafts(BaseModel):
    """
    Response model for the section call.

    The LLM sees the full SectionDrafts schema (so its output is structured as before),
    but the response is only parsed as a list of dicts. Each draft is then validated
    on its own, so one bad draft no longer rejects the whole section.
    """

    drafts: list[dict[str, Any]] = Field(default_factory=list)

    @classmethod
    def model_json_schema(cls, *args, **kwargs):  # used for the tool definition
        return SectionDrafts.model_json_schema(*args, **kwargs)


PROMPT_VERSION = "v3"


def load_prompt_template() -> str:
    """Load section drafts prompt template"""
    prompt_path = Path("prompts/section_drafts.md")
    with open(prompt_path) as f:
        return f.read()


def load_scope_rules() -> dict:
    """Load scope.yaml if it exists"""
    import yaml

    scope_path = Path("data/scope.yaml")
    if scope_path.exists():
        with open(scope_path) as f:
            return yaml.safe_load(f) or {}
    return {}


def is_section_excluded(page: str, section_heading: str, scope_rules: dict) -> bool:
    """Check if a section should be excluded"""
    exclude_sections = scope_rules.get("exclude_sections", [])
    for rule in exclude_sections:
        if rule["page"] == page:
            if (
                "heading_contains" in rule
                and rule["heading_contains"].lower() in section_heading.lower()
            ):
                return True
    return False


def is_sentence_excluded(text: str, scope_rules: dict) -> bool:
    """Check if a sentence matches exclusion patterns"""
    import re

    patterns = scope_rules.get("exclude_sentence_patterns", [])
    for pattern in patterns:
        if re.search(pattern, text, re.IGNORECASE):
            return True
    return False


def make_section_key(content_id: str, section_path: str) -> str:
    """Create stable section key for grouping and draft IDs"""
    hash_input = f"{content_id}|{section_path}"
    return hashlib.sha1(hash_input.encode()).hexdigest()[:10]


def make_draft_id(section_key: str, seq: int) -> str:
    """Create draft ID: d{section_key}{seq:02d}"""
    return f"d{section_key}{seq:02d}"


def format_sentences(
    sentences: list[dict], flagged_ids: set[str], out_of_scope_ids: set[str]
) -> str:
    """
    Format sentences for the prompt.

    Args:
        sentences: List of sentence dicts with evidence_id and text
        flagged_ids: Set of evidence_ids that are flagged (keep=Y)
        out_of_scope_ids: Set of evidence_ids with keep=N

    Returns:
        Formatted string with annotations
    """
    lines = []
    for sent in sentences:
        eid = sent["evidence_id"]
        text = sent["text"]

        if eid in out_of_scope_ids:
            lines.append(f"[{eid}] (out of scope – context only, do not cite) {text}")
        elif eid in flagged_ids:
            # Get labels if available
            label_str = sent.get("label", "")
            if label_str:
                lines.append(f"[{eid}] (flagged: {label_str}) {text}")
            else:
                lines.append(f"[{eid}] (flagged) {text}")
        else:
            lines.append(f"[{eid}] {text}")

    return "\n".join(lines)


def build_prompt(
    base_path: str,
    section_path: str,
    parent_heading: str,
    sentences: list[dict],
    flagged_ids: set[str],
    out_of_scope_ids: set[str],
) -> str:
    """Build the complete prompt for one section"""
    template = load_prompt_template()

    sentences_str = format_sentences(sentences, flagged_ids, out_of_scope_ids)

    return template.format(
        base_path=base_path,
        section_path=section_path,
        parent_heading=parent_heading or "(none)",
        sentences=sentences_str,
    )


def check_evidence_and_journeys(
    draft: TaskBody,
    section_evidence_ids: set[str],
    out_of_scope_ids: set[str] = frozenset(),
) -> list[str]:
    """
    Evidence and journey checks for a single draft.

    Returns list of error messages (empty if all OK).
    """
    errors = []

    # Check: all cited evidence IDs are from this section
    all_cited = set(draft.evidence)

    # Collect IDs from nested structures
    if draft.window:
        if draft.window.opens:
            all_cited.update(draft.window.opens.evidence)
        if draft.window.closes:
            all_cited.update(draft.window.closes.evidence)

    if draft.duration:
        all_cited.update(draft.duration.evidence)

    for req in draft.requires:
        all_cited.update(req.evidence)

    for exp in draft.expectations:
        all_cited.update(exp.evidence)

    for sub in draft.sub_tasks:
        all_cited.update(sub.evidence)
        if sub.window:
            if sub.window.opens:
                all_cited.update(sub.window.opens.evidence)
            if sub.window.closes:
                all_cited.update(sub.window.closes.evidence)

    for guide in draft.guidance:
        all_cited.update(guide.evidence)

    # Check all cited IDs are in section
    invalid_ids = all_cited - section_evidence_ids
    if invalid_ids:
        errors.append(f"Draft cites evidence not in this section: {sorted(invalid_ids)}")

    excluded = all_cited & out_of_scope_ids
    if excluded:
        errors.append(f"Draft cites out-of-scope sentences: {sorted(excluded)}")

    # Check: journeys consistency
    if "typical" in draft.journeys:
        special = {"neonatal", "loss", "abroad", "surrogacy"}
        if any(j in draft.journeys for j in special):
            errors.append(
                f"Journey 'typical' appears with special-circumstance tags: {draft.journeys}"
            )

    return errors


def process_section(
    base_path: str,
    content_id: str,
    section_path: str,
    parent_heading: str,
    sentences: list[dict],
    flagged_ids: set[str],
    out_of_scope_ids: set[str],
    *,
    model_id: str | None = None,
    region: str | None = None,
) -> tuple[list[Draft], list[dict]]:
    """
    Process one section: make LLM call, validate each draft, return (ok_drafts, rejected_records).

    Args:
        base_path: Page path
        content_id: Page content ID
        section_path: Full section path (e.g. "How to claim > What you'll need")
        parent_heading: Parent section heading or empty string
        sentences: All sentences in this section
        flagged_ids: Evidence IDs with keep=Y
        out_of_scope_ids: Evidence IDs with keep=N
        model_id: Bedrock model ID
        region: AWS region

    Returns:
        (ok drafts, rejected records). A rejected record is a dict with draft_id, source,
        reason ("invalid_draft" or "call_failed"), errors and the raw LLM output.
    """
    # Build prompt
    prompt = build_prompt(
        base_path, section_path, parent_heading, sentences, flagged_ids, out_of_scope_ids
    )

    system = """You are extracting structured task records from GOV.UK content.

Focus on citizen actions. Follow the window rules exactly (signed offsets, notice periods as closes).
Only tag journeys when explicitly mentioned. Cite evidence IDs for every field.

Return 0-n tasks as the section genuinely contains."""

    section_key = make_section_key(content_id, section_path)
    cache_payload = {
        "sentences": [s["evidence_id"] for s in sentences],
        "flagged": sorted(flagged_ids),
        "out_of_scope": sorted(out_of_scope_ids),
    }
    cache_key = make_cache_key("drafts", PROMPT_VERSION, model_id or "default", cache_payload)

    section_evidence_ids = {s["evidence_id"] for s in sentences}
    evidence_texts = {s["evidence_id"]: s["text"] for s in sentences}
    max_tokens = 8192 if len(sentences) > 30 else 4096

    def call(prompt_text: str, key: str):
        return call_structured(
            LooseSectionDrafts,
            prompt=prompt_text,
            system=system,
            max_tokens=max_tokens,
            check=None,  # drafts are validated one by one below
            retries=0,
            cache_key=key,
            model_id=model_id,
            region=region,
        )

    def validate_all(raw_drafts: list[dict]) -> list[tuple[int, dict, TaskBody | None, list[str]]]:
        out = []
        for i, raw in enumerate(raw_drafts, 1):
            body, errors = validate_one(raw, section_evidence_ids, evidence_texts, out_of_scope_ids)
            out.append((i, raw, body, errors))
        return out

    # Attempt 1
    attempts: list[list[tuple[int, dict, TaskBody | None, list[str]]]] = []
    call_errors: list[str] = []
    first = call(prompt, cache_key)
    if first.value is not None:
        attempts.append(validate_all(first.value.drafts))
    else:
        call_errors = list(first.errors or ["response could not be parsed"])

    # Attempt 2: only if the call failed or some drafts were invalid
    failing = (
        []
        if not attempts
        else [(i, raw, errs) for i, raw, body, errs in attempts[0] if body is None]
    )
    if call_errors or failing:
        if failing:
            feedback = "\n".join(
                f"- draft {i} (title: {raw.get('title', '?')!r}): " + "; ".join(errs)
                for i, raw, errs in failing
            )
        else:
            feedback = "\n".join(f"- {e}" for e in call_errors)
        retry_prompt = (
            prompt
            + "\n\n## Your previous answer had these errors\n\n"
            + feedback
            + "\n\nReturn corrected drafts for the WHOLE section (all tasks, not only the corrected ones)."
        )
        second = call(retry_prompt, cache_key + "-retry1")
        if second.value is not None:
            attempts.append(validate_all(second.value.drafts))
        elif not attempts:
            call_errors += list(second.errors or [])

    def source_for(draft_id: str) -> Source:
        return Source(base_path=base_path, section_path=section_path, draft_id=draft_id)

    if not attempts:
        # Neither call returned anything usable: record the section as rejected
        draft_id = make_draft_id(section_key, 1)
        return [], [
            {
                "draft_id": draft_id,
                "source": source_for(draft_id).model_dump(),
                "status": "rejected",
                "reason": "call_failed",
                "errors": call_errors,
                "raw": None,
            }
        ]

    # Use the attempt with the fewest invalid drafts (then the most valid ones)
    best = min(attempts, key=lambda att: (sum(b is None for _, _, b, _ in att), -len(att)))

    from src.task_inventory.schema import convert_qualifying_week

    ok: list[Draft] = []
    rejected: list[dict] = []
    for i, raw, body, errors in best:
        draft_id = make_draft_id(section_key, i)
        if body is None:
            rejected.append(
                {
                    "draft_id": draft_id,
                    "source": source_for(draft_id).model_dump(),
                    "status": "rejected",
                    "reason": "invalid_draft",
                    "errors": errors,
                    "raw": raw,
                }
            )
            continue
        # Convert qualifying_week anchors to due_week (after the window checks)
        convert_qualifying_week(body)
        ok.append(
            Draft(
                **body.model_dump(),
                draft_id=draft_id,
                source=source_for(draft_id),
                status="ok",
                errors=[],
            )
        )
    return ok, rejected


def validate_one(
    raw: dict,
    section_evidence_ids: set[str],
    evidence_texts: dict[str, str],
    out_of_scope_ids: set[str],
) -> tuple[TaskBody | None, list[str]]:
    """
    Validate one draft from the LLM response.

    Repairs applied first (in code, not by the LLM):
    - normalise() (synonyms, long titles, unknown policy, relative URLs), if available
    - 'typical' is removed when a special-circumstance journey is also tagged

    Returns (TaskBody, []) if valid, or (None, errors).
    """
    raw = dict(raw)
    if _normalise is not None:
        raw = _normalise(raw) or raw

    journeys = raw.get("journeys") or []
    if "typical" in journeys and SPECIAL_JOURNEYS & set(journeys):
        raw["journeys"] = [j for j in journeys if j != "typical"]

    try:
        body = TaskBody.model_validate(raw)
    except ValidationError as e:
        return None, [
            f"schema: {'.'.join(str(p) for p in err['loc'])}: {err['msg']}" for err in e.errors()
        ]

    errors = check_evidence_and_journeys(body, section_evidence_ids, out_of_scope_ids)
    content_errors, _warnings = check_draft_content(body, evidence_texts)
    errors.extend(content_errors)  # window number/unit/direction errors reject the draft
    return (None, errors) if errors else (body, [])


def run_section_drafts(
    sentences_path: str = "data/sentences_extracted.csv",
    candidates_path: str = "data/candidates.csv",
    output_dir: str = "data/runs/latest",
    pages: list[str] | None = None,
    *,
    model_id: str | None = None,
    region: str | None = None,
) -> dict[str, Any]:
    """
    Run stage 3: section drafts.

    Args:
        sentences_path: Path to sentences CSV
        candidates_path: Path to candidates CSV
        output_dir: Output directory for this run
        pages: Optional list of base_paths to filter to (for M1)
        model_id: Bedrock model ID
        region: AWS region

    Returns:
        Dict with counts and summary
    """
    import pandas as pd

    # Load scope rules
    scope_rules = load_scope_rules()

    # Load data
    sentences_df = pd.read_csv(sentences_path)
    candidates_df = pd.read_csv(candidates_path)

    # Filter to specified pages if provided
    if pages:
        sentences_df = sentences_df[sentences_df["base_path"].isin(pages)]
        candidates_df = candidates_df[candidates_df["page"].isin(pages)]

    # Build lookup: evidence_id -> keep status and label
    keep_map = {}
    label_map = {}
    for _, row in candidates_df.iterrows():
        eid = row["evidence_id"]  # Note: candidates use 'evidence_ids' column
        keep_map[eid] = row.get("keep", "Y")
        labels = row.get("labels", row.get("label", ""))
        label_map[eid] = labels if isinstance(labels, str) else ""

    # Build sections
    sections = defaultdict(
        lambda: {"sentences": [], "flagged_ids": set(), "out_of_scope_ids": set()}
    )

    for _, row in sentences_df.iterrows():
        eid = row["evidence_id"]
        content_id = row["content_id"]
        base_path = row["base_path"]
        section_heading = row["section_path"]

        # Build section_path (simplified for now - just use section_heading)
        section_path = section_heading

        section_key = (content_id, base_path, section_path)

        sections[section_key]["sentences"].append(
            {"evidence_id": eid, "text": row["text"], "label": label_map.get(eid, "")}
        )

        # Track flagged and out-of-scope
        keep_status = keep_map.get(eid, "Y")

        # Check if sentence matches exclusion patterns
        if is_sentence_excluded(row["text"], scope_rules):
            sections[section_key]["out_of_scope_ids"].add(eid)
        elif keep_status == "Y":
            sections[section_key]["flagged_ids"].add(eid)
        elif keep_status == "N":
            sections[section_key]["out_of_scope_ids"].add(eid)

    # Process sections with at least one keep=Y candidate
    ok_drafts: list[Draft] = []
    rejected_drafts: list[dict] = []
    sections_called = 0
    sections_called_keys = []
    sections_skipped = 0
    sections_excluded = 0

    print(f"\n{'=' * 80}")
    print("Stage 3: Section Drafts")
    print(f"{'=' * 80}\n")
    print(f"Found {len(sections)} sections total")

    for (content_id, base_path, section_path), section_data in sorted(sections.items()):
        # Check if section is excluded by scope rules
        if is_section_excluded(base_path, section_path, scope_rules):
            sections_excluded += 1
            continue

        if not section_data["flagged_ids"]:
            sections_skipped += 1
            continue

        sections_called += 1
        sections_called_keys.append(f"{base_path} > {section_path}")
        print(f"\nSection {sections_called}: {base_path} > {section_path}")
        print(
            f"  {len(section_data['sentences'])} sentences, {len(section_data['flagged_ids'])} flagged"
        )

        section_ok, section_rejected = process_section(
            base_path=base_path,
            content_id=content_id,
            section_path=section_path,
            parent_heading="",  # TODO: extract from hierarchy
            sentences=section_data["sentences"],
            flagged_ids=section_data["flagged_ids"],
            out_of_scope_ids=section_data["out_of_scope_ids"],
            model_id=model_id,
            region=region,
        )

        ok_drafts.extend(section_ok)
        rejected_drafts.extend(section_rejected)
        print(f"  → {len(section_ok)} drafts ok, {len(section_rejected)} rejected")

    # Save outputs
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)

    # Write drafts.jsonl
    with open(output_path / "drafts.jsonl", "w") as f:
        for draft in ok_drafts:
            f.write(draft.model_dump_json() + "\n")

    # Write drafts_rejected.jsonl
    with open(output_path / "drafts_rejected.jsonl", "w") as f:
        for record in rejected_drafts:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")

    summary = {
        "prompt_version": PROMPT_VERSION,
        "sections_total": len(sections),
        "sections_called": sections_called,
        "sections_excluded": sections_excluded,
        "sections_skipped": sections_skipped,
        "drafts_ok": len(ok_drafts),
        "drafts_rejected": len(rejected_drafts),
        "sections_with_rejections": sorted(
            {f"{r['source']['base_path']} > {r['source']['section_path']}" for r in rejected_drafts}
        ),
    }
    with open(output_path / "stage3_summary.json", "w") as f:
        json.dump(summary, f, indent=2)

    print(f"\n{'=' * 80}")
    print("✓ Stage 3 complete")
    print(f"{'=' * 80}\n")
    print(f"Sections called: {sections_called}")
    print(f"Sections excluded by scope: {sections_excluded}")
    print(f"Sections skipped (no keep=Y): {sections_skipped}")
    print(f"Drafts OK: {len(ok_drafts)}")
    print(f"Drafts rejected: {len(rejected_drafts)}")
    print("\nOutput:")
    print(f"  {output_path / 'drafts.jsonl'}")
    print(f"  {output_path / 'drafts_rejected.jsonl'}")

    return summary
