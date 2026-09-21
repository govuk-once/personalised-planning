"""
Stage 2: Candidate Flagging

Reads the sentences CSV produced by stage 0-1 and flags sentences that are likely
citizen actions or deadlines.  Two methods are combined:
  1. Pattern matching  — modal verbs, imperative verbs, deadline phrases, CTA links.
  2. LLM extraction   — one structured Bedrock call per (base_path, section_index) group.
Results are merged; each candidate is marked flagged_by='pattern', 'llm', or 'both'.
LLM labels take precedence when a sentence is flagged by both methods.

Key functions:
- flag_candidates_from_sentences(sentences_path, output_path, use_llm, model_id, region)
      Top-level entry point called by scripts/task_inventory/run_pipeline.py.
- flag_section_by_llm(section_sentences, model_id, region)
      Runs one LLM call for a single section; returns list of {evidence_id, labels}.
- merge_pattern_and_llm_candidates(pattern_df, llm_candidates, sentences_df)
      Union-merges both result sets into a single DataFrame.
- infer_policy(section_path, page_path, text)
      Heuristic policy tagger based on keyword matching (used for pattern-only rows).

Run via:
    python scripts/task_inventory/run_pipeline.py --stage candidates

Assumptions:
- Input  data/sentences.csv  (produced by stage 0-1).
- Output data/candidates.csv  with columns: evidence_id, policy, page,
  section_path, text, labels, flagged_by, keep, keep_reason, text_key.
- 'keep' column defaults to 'Y'; set to 'N' manually to exclude out-of-scope rows
  before running stage 3.
- LLM mode requires AWS Bedrock credentials in the environment and a reachable
  eu-west-2 endpoint.  Disable with use_llm=False for offline/cheap runs.
- Default model: eu.anthropic.claude-sonnet-4-0 (override via model_id arg or
  ANTHROPIC_MODEL env var).
"""

import re

import pandas as pd
from pydantic import BaseModel, Field

from src.task_inventory.llm import call_structured

# Pattern definitions
PATTERNS = {
    "modal_verbs": [
        r"\bmust\b",
        r"\bneed to\b",
        r"\bshould\b",
        r"\bhave to\b",
        r"\brequired to\b",
        r"\bobliged to\b",
    ],
    "imperatives": [
        # Action verbs from schema.VERBS
        r"\bcheck\b",
        r"\btell\b",
        r"\bgive notice\b",
        r"\bclaim\b",
        r"\bapply\b",
        r"\bregister\b",
        r"\border\b",
        r"\bplan\b",
        r"\breport\b",
        r"\btake\b",
        r"\bchallenge\b",
        r"\bget help\b",
        r"\bsend\b",
        r"\bcontact\b",
        r"\binform\b",
        r"\bnotify\b",
        r"\bsubmit\b",
        r"\bprovide\b",
        r"\bcomplete\b",
        r"\bfill\b",
        r"\bwork out\b",
        r"\bfind out\b",
        r"\bkeep\b",
        r"\breturn\b",
    ],
    "deadline_phrases": [
        r"within \d+\s+(day|week|month|year)s?",
        r"at least \d+\s+(day|week|month|year)s?",
        r"by the \d+\w+\s+(day|week|month)",
        r"before (the )?\d+\s+(day|week|month|year)s?",
        r"after (the )?\d+\s+(day|week|month|year)s?",
        r"(up to|no more than) \d+\s+(day|week|month|year)s?",
        r"backdated? (up to|for) \d+",
        r"\d+\s+(day|week|month|year)s? (before|after|from)",
        r"by (the )?(qualifying week|due date|birth)",
        r"(as soon as|immediately after)",
    ],
    "cta_links": [
        r"/apply-",
        r"/claim-",
        r"/register-",
        r"/report-",
        r"/check-",
        r"-calculator",
        r"-checker",
        r"/how-to-claim",
        r"/eligibility",
        r"/start",
    ],
}


def infer_policy(section_path: str, page_path: str, text: str) -> str | None:
    """
    Infer policy from content using word boundaries.

    Policies:
    - Maternity Allowance
    - Statutory Maternity Pay
    - Maternity Leave
    - Paternity Leave and Pay
    - Shared Parental Leave and Pay
    - Neonatal Care Leave and Pay
    - Bereaved Partner's Paternity Leave and Pay
    - Parental Leave
    - Stillbirth Registration
    - Birth Registration
    - Child Benefit
    - Universal Credit
    - Sure Start Maternity Grant
    - Healthy Start
    - Certificates
    - Antenatal Rights
    - Employment Rights
    """
    combined = f"{section_path} {page_path} {text}".lower()

    # Order matters - check specific before general
    # Use word boundaries to avoid false matches

    # Maternity benefits
    if "maternity allowance" in combined or "/maternity-allowance" in page_path:
        return "Maternity Allowance"
    if "statutory maternity pay" in combined or re.search(r"\bsmp\b", combined):
        return "Statutory Maternity Pay"
    if "maternity leave" in combined or "maternity-leave" in page_path:
        return "Maternity Leave"

    # Paternity benefits
    if "bereaved partner" in combined or "bereavement" in combined:
        return "Bereaved Partner's Paternity Leave and Pay"
    if "paternity" in combined:
        return "Paternity Leave and Pay"

    # Parental leave
    if (
        "shared parental" in combined
        or re.search(r"\bspl\b", combined)
        or re.search(r"\bshpp\b", combined)
    ):
        return "Shared Parental Leave and Pay"
    if "neonatal" in combined:
        return "Neonatal Care Leave and Pay"
    if re.search(r"\bparental leave\b", combined) and "shared" not in combined:
        return "Parental Leave"

    # Registration
    if "stillbirth" in combined or "stillborn" in combined:
        return "Stillbirth Registration"
    if "register" in combined and "birth" in combined:
        return "Birth Registration"

    # Financial support
    if "child benefit" in combined or "/child-benefit" in page_path:
        return "Child Benefit"
    if "universal credit" in combined:
        return "Universal Credit"
    if "sure start maternity grant" in combined or "/sure-start-maternity-grant" in page_path:
        return "Sure Start Maternity Grant"
    if "healthy start" in combined or "/healthy-start" in page_path:
        return "Healthy Start"

    # Documents
    if "certificate" in combined or "matb1" in combined or "mat b1" in combined:
        return "Certificates"

    # Rights
    if "antenatal" in combined or "time off for appointments" in combined:
        return "Antenatal Rights"
    if "employment rights" in combined or "employee rights" in combined:
        return "Employment Rights"

    return None


# LLM flagging schema
class LLMCandidate(BaseModel):
    evidence_id: str = Field(description="Evidence ID from the section")
    labels: list[str] = Field(description="One or more of: action, deadline, context")


class LLMFlaggingResult(BaseModel):
    candidates: list[LLMCandidate]


def flag_section_by_llm(section_sentences: pd.DataFrame, model_id: str, region: str) -> list[dict]:
    """
    Flag candidates in one section using LLM.

    Args:
        section_sentences: DataFrame rows for one section (base_path + section_path)
        model_id: Bedrock model ID
        region: AWS region

    Returns:
        List of candidate dicts with 'evidence_id' and 'labels'
    """
    if len(section_sentences) == 0:
        return []

    # Build prompt
    section_path = section_sentences.iloc[0]["section_path"]
    base_path = section_sentences.iloc[0]["base_path"]

    prompt_parts = [
        "# Task Candidate Extraction\n\n",
        f"**Page**: {base_path}\n",
        f"**Section**: {section_path}\n\n",
        "Below are sentences from this section. Each has an evidence ID.\n\n",
        "**Your task**: List every snippet that:\n",
        "1. Tells a citizen to **do something** → label: action\n",
        "2. Sets a **deadline or time window** → label: deadline\n",
        "3. States **eligibility/conditions** (context, not actionable) → label: context\n\n",
        "A sentence can have multiple labels (e.g., action + deadline).\n\n",
        "## Sentences\n\n",
    ]

    for _, row in section_sentences.iterrows():
        prompt_parts.append(f"**{row['evidence_id']}**: {row['text']}\n\n")

    prompt_parts.append(
        "\n## Instructions\n\n"
        "- Only flag relevant snippets (skip purely descriptive text)\n"
        "- If a sentence has both action and deadline, include both labels\n"
        "- Return evidence_ids and labels\n"
    )

    prompt = "".join(prompt_parts)

    try:
        result = call_structured(
            LLMFlaggingResult,
            prompt=prompt,
            model_id=model_id,
            region=region,
            system="You extract task candidates from GOV.UK content: actions, deadlines, conditions.",
        )

        if not result.value:
            return []

        # Convert to dicts
        candidates = []
        for llm_cand in result.value.candidates:
            candidates.append({"evidence_id": llm_cand.evidence_id, "labels": llm_cand.labels})

        return candidates

    except Exception as e:
        print(f"  ⚠️  LLM flagging failed for {section_path}: {e}")
        return []


def merge_pattern_and_llm_candidates(
    pattern_candidates: pd.DataFrame, llm_candidates: list[dict], sentences_df: pd.DataFrame
) -> pd.DataFrame:
    """
    Merge pattern and LLM candidates.

    - If same evidence_id flagged by both → flagged_by='both', use LLM labels
    - If only pattern → flagged_by='pattern'
    - If only LLM → flagged_by='llm', lookup metadata from sentences_df
    """
    # Index pattern candidates by evidence_id
    pattern_by_eid = pattern_candidates.set_index("evidence_id").to_dict("index")

    # Index LLM candidates by evidence_id
    llm_by_eid = {}
    for llm_cand in llm_candidates:
        eid = llm_cand["evidence_id"]
        llm_by_eid[eid] = llm_cand

    # Index sentences by evidence_id for LLM-only lookups
    sentences_by_eid = sentences_df.set_index("evidence_id").to_dict("index")

    # Merge
    merged = []
    all_eids = set(pattern_by_eid.keys()) | set(llm_by_eid.keys())

    for eid in all_eids:
        pattern_cand = pattern_by_eid.get(eid)
        llm_cand = llm_by_eid.get(eid)

        if pattern_cand and llm_cand:
            # Both flagged
            merged.append(
                {
                    "evidence_id": eid,
                    "policy": pattern_cand["policy"],
                    "page": pattern_cand["page"],
                    "section_path": pattern_cand["section_path"],
                    "text": pattern_cand["text"],
                    "labels": "|".join(llm_cand["labels"]),  # Prefer LLM labels
                    "flagged_by": "both",
                    "keep": "Y",
                    "keep_reason": "",
                    "text_key": pattern_cand["text_key"],
                }
            )
        elif pattern_cand:
            # Pattern only
            merged.append(pattern_cand)
        elif llm_cand:
            # LLM only - lookup metadata from sentences
            sent = sentences_by_eid.get(eid)
            if sent:
                policy = infer_policy(sent["section_path"], sent["base_path"], sent["text"])
                merged.append(
                    {
                        "evidence_id": eid,
                        "policy": policy or "",
                        "page": sent["base_path"],
                        "section_path": sent["section_path"],
                        "text": sent["text"],
                        "labels": "|".join(llm_cand["labels"]),
                        "flagged_by": "llm",
                        "keep": "Y",
                        "keep_reason": "",
                        "text_key": sent["text_key"],
                    }
                )

    return pd.DataFrame(merged)


def flag_candidates_from_sentences(
    sentences_path: str = "data/sentences.csv",
    output_path: str = "data/candidates.csv",
    use_llm: bool = True,
    model_id: str = "eu.anthropic.claude-sonnet-4-0",
    region: str = "eu-west-2",
) -> dict:
    """
    Flag candidates from sentences using pattern + optional LLM.

    Args:
        sentences_path: Path to sentences.csv
        output_path: Where to write candidates.csv
        use_llm: If True, also run LLM flagging per section
        model_id: Bedrock model ID
        region: AWS region

    Returns:
        Dict with counts: sentences, candidates, flagged_rate
    """
    print(f"\n{'=' * 80}")
    print("Stage 2: Candidate Flagging")
    print(f"{'=' * 80}\n")

    # Load sentences
    df = pd.read_csv(sentences_path)
    print(f"Loaded {len(df)} sentences")
    print(f"Method: {'pattern + LLM' if use_llm else 'pattern only'}\n")

    # Step 1: Pattern flagging
    print("Step 1: Pattern flagging...")
    pattern_candidates = []

    for _, row in df.iterrows():
        evidence_id = row["evidence_id"]
        text = row["text"]
        text_lower = text.lower()
        base_path = row["base_path"]
        section_path = row["section_path"]
        text_key = row["text_key"]

        # Check each pattern type
        matches = {
            "modal": any(re.search(p, text_lower) for p in PATTERNS["modal_verbs"]),
            "imperative": any(re.search(p, text_lower) for p in PATTERNS["imperatives"]),
            "deadline": any(re.search(p, text_lower) for p in PATTERNS["deadline_phrases"]),
            "cta": any(p in base_path for p in PATTERNS["cta_links"]),
        }

        if not any(matches.values()):
            continue

        # Determine labels (can be multiple)
        labels = []
        if matches["deadline"]:
            labels.append("deadline")
        if matches["imperative"] or matches["cta"] or matches["modal"]:
            # Check if it's about eligibility/conditions
            if any(
                word in text_lower for word in ["eligible", "eligibility", "qualify", "entitled"]
            ):
                labels.append("context")
            else:
                labels.append("action")

        # Default to action if nothing else matched
        if not labels:
            labels.append("action")

        # Infer policy
        policy = infer_policy(section_path, base_path, text)

        pattern_candidates.append(
            {
                "evidence_id": evidence_id,
                "policy": policy or "",
                "page": base_path,
                "section_path": section_path,
                "text": text,
                "labels": "|".join(labels),
                "flagged_by": "pattern",
                "keep": "Y",
                "keep_reason": "",
                "text_key": text_key,
            }
        )

    pattern_df = pd.DataFrame(pattern_candidates)
    print(f"  Flagged {len(pattern_df)} candidates by pattern")

    # Step 2: LLM flagging (if enabled)
    if use_llm:
        print("\nStep 2: LLM flagging per section...")

        # Group sentences by (base_path, section_index) to get sections
        sections = df.groupby(["base_path", "section_index"])
        total_sections = len(sections)

        all_llm_candidates = []
        sections_called = 0

        for (_base_path, _section_index), section_df in sections:
            sections_called += 1
            section_path = section_df.iloc[0]["section_path"]

            if sections_called % 10 == 0:
                print(f"  {sections_called}/{total_sections} sections...")

            llm_cands = flag_section_by_llm(section_df, model_id, region)
            all_llm_candidates.extend(llm_cands)

        print(f"  Flagged {len(all_llm_candidates)} candidates by LLM")

        # Step 3: Merge pattern + LLM
        print("\nStep 3: Merging pattern + LLM results...")
        candidates_df = merge_pattern_and_llm_candidates(pattern_df, all_llm_candidates, df)
        print(f"  Final: {len(candidates_df)} candidates")
    else:
        candidates_df = pattern_df

    # Save
    candidates_df.to_csv(output_path, index=False)

    flagged_rate = len(candidates_df) / len(df) * 100 if len(df) > 0 else 0

    print(f"\n{'=' * 80}")
    print("✓ Candidate flagging complete")
    print(f"{'=' * 80}\n")
    print(f"Total sentences: {len(df)}")
    print(f"Candidates flagged: {len(candidates_df)} ({flagged_rate:.1f}%)")

    if use_llm:
        print("\nBy method:")
        method_counts = candidates_df["flagged_by"].value_counts()
        for method in ["pattern", "llm", "both"]:
            count = method_counts.get(method, 0)
            print(f"  {method}: {count}")

    print("\nLabel breakdown:")
    for label in ["action", "deadline", "context"]:
        count = sum(label in row["labels"] for _, row in candidates_df.iterrows())
        print(f"  {label}: {count}")

    print("\nPolicy breakdown:")
    policy_counts = candidates_df["policy"].value_counts()
    for policy, count in policy_counts.head(10).items():
        if policy:
            print(f"  {policy}: {count}")

    print(f"\n{'=' * 80}")
    print(f"Output: {output_path}")
    print(f"{'=' * 80}\n")
    print("Next step: Review candidates.csv, mark keep='N' for out-of-scope")

    # Stats for return
    method_counts_dict = candidates_df["flagged_by"].value_counts().to_dict()

    return {
        "sentences": len(df),
        "candidates": len(candidates_df),
        "flagged_rate": flagged_rate,
        "pattern_only": method_counts_dict.get("pattern", 0) if use_llm else len(candidates_df),
        "llm_only": method_counts_dict.get("llm", 0) if use_llm else 0,
        "both": method_counts_dict.get("both", 0) if use_llm else 0,
    }
