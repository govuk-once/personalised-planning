"""
Stage 0-1: Section Extraction

Parses GOV.UK pages from a subgraph JSON file, splits them into sentences, and
writes a sentences CSV.  Handles both standard pages (details.body) and guide
pages (details.parts array) — each guide part becomes a top-level section, with
##/### headings as subsections.

Key functions:
- extract_sections_from_subgraph(subgraph_path, output_path)
      Top-level entry point called by scripts/task_inventory/run_pipeline.py.
- extract_sentences_from_page(page)
      Parses one node dict into a list of Sentence objects.
- extract_sections_from_body(body_text, ...)
      Splits a Govspeak body into per-section Sentence lists.
- split_into_sentences(text)
      Sentence/list-item splitter that handles Govspeak callouts.
- generate_evidence_id(...)
      Produces stable IDs of the form s{hash8}{seq:04d}.
- generate_text_key(base_path, text)
      sha1-based key for cross-run deduplication matching.

Run via:
    python scripts/task_inventory/run_pipeline.py --stage sections

Assumptions:
- Subgraph JSON must have a top-level "nodes" array; each node is a page dict
  with at least base_path, content_id, and details (as a JSON string or dict).
- details.parts[*].body is a [govspeak, html] array; govspeak[0].content is used.
- Output CSV columns: evidence_id, content_id, base_path, part, section_path,
  section_level, section_index, seq, text, text_key, source_updated.
- Default paths: input  data/having_a_baby_subgraph.json
                 output data/sentences.csv
"""

import hashlib
import json
import re
from dataclasses import dataclass


@dataclass
class Sentence:
    """A single sentence with evidence ID and metadata"""

    evidence_id: str
    content_id: str
    base_path: str
    part: str  # Part slug for guides, empty for standard pages
    section_path: str  # "Part > Section" or just "Section"
    section_level: int  # 2 for ##, 3 for ###
    section_index: int  # Position within page (continuous)
    seq: int  # Sequence within section
    text: str
    text_key: str
    source_updated: str | None


def slugify(text: str) -> str:
    """Convert text to URL-friendly slug"""
    text = text.lower().strip()
    text = re.sub(r"[^\w\s-]", "", text)
    text = re.sub(r"[\s_]+", "-", text)
    return text.strip("-")


def normalize_text_for_key(text: str) -> str:
    """
    Normalize text for text_key generation.

    Removes: extra whitespace, punctuation, case
    Keeps: words, basic structure
    """
    # Lowercase
    text = text.lower()
    # Remove URLs
    text = re.sub(r"https?://[^\s]+", "", text)
    # Remove markdown links but keep text
    text = re.sub(r"\[([^\]]+)\]\([^\)]+\)", r"\1", text)
    # Collapse whitespace
    text = re.sub(r"\s+", " ", text)
    # Remove most punctuation except apostrophes in words
    text = re.sub(r"[^\w\s\']", "", text)
    return text.strip()


def generate_text_key(base_path: str, text: str) -> str:
    """
    Generate stable text_key for carry-over matching.

    Format: sha1(base_path + normalized_text)[:12]
    """
    normalized = normalize_text_for_key(text)
    combined = f"{base_path}:{normalized}"
    return hashlib.sha1(combined.encode()).hexdigest()[:12]


def generate_evidence_id(
    content_id: str, part_slug: str, section_path: str, section_index: int, seq: int
) -> str:
    """
    Generate stable evidence ID.

    Format: s{sha1(content_id, part_slug, section_path, section_index)[:8]}{seq:04d}

    Args:
        content_id: GOV.UK content UUID
        part_slug: Slugified part title (empty for non-guides)
        section_path: Full section path (e.g., "Overview > Eligibility")
        section_index: Position of section within page
        seq: Sentence number within section
    """
    combined = f"{content_id}:{part_slug}:{section_path}:{section_index}"
    hash_obj = hashlib.sha1(combined.encode())
    hash_prefix = hash_obj.hexdigest()[:8]
    return f"s{hash_prefix}{seq:04d}"


def clean_govspeak_markers(text: str) -> str:
    """Remove Govspeak formatting markers"""
    # Remove callout markers
    text = re.sub(r"^\s*[$%^]\s*", "", text, flags=re.MULTILINE)
    # Remove emphasis markers
    text = re.sub(r"\*\*(.+?)\*\*", r"\1", text)  # bold
    text = re.sub(r"\*(.+?)\*", r"\1", text)  # italic
    # Collapse whitespace
    text = re.sub(r"\s+", " ", text).strip()
    return text


def split_into_sentences(text: str) -> list[str]:
    """
    Split text into sentences and list items.

    Handles:
    - Standard sentences
    - List items (-, *, +, numbered)
    - Govspeak callouts (^, $, %)
    """
    sentences = []
    lines = text.split("\n")

    for line in lines:
        line = line.strip()
        if not line or len(line) < 10:
            continue

        # Check if it's a list item or callout
        is_list_item = bool(re.match(r"^[-*+$%^]|\d+\.", line))

        if is_list_item:
            cleaned = clean_govspeak_markers(line)
            if len(cleaned) >= 10:
                sentences.append(cleaned)
        else:
            # Split by sentence boundaries
            chunks = re.split(r"([.!?])\s+", line)
            current = ""
            for chunk in chunks:
                if chunk in ".!?":
                    current += chunk
                    if current.strip() and len(current.strip()) >= 10:
                        sentences.append(clean_govspeak_markers(current.strip()))
                    current = ""
                else:
                    current += chunk

            if current.strip() and len(current.strip()) >= 10:
                sentences.append(clean_govspeak_markers(current.strip()))

    return sentences


def extract_sections_from_body(
    body_text: str,
    content_id: str,
    base_path: str,
    part_title: str = "",
    part_slug: str = "",
    section_index_start: int = 1,
    source_updated: str | None = None,
) -> tuple[list[Sentence], int]:
    """
    Extract sections from govspeak body text.

    Args:
        body_text: Govspeak markdown
        content_id: GOV.UK content UUID
        base_path: Page path
        part_title: Part title (for guides)
        part_slug: Part slug (for guides)
        section_index_start: Starting section index
        source_updated: ISO date string

    Returns:
        (sentences, next_section_index)
    """
    sentences = []
    section_index = section_index_start

    # Pattern for ## and ### headings
    heading_pattern = re.compile(r"^(#{2,3})\s+(.+)$", re.MULTILINE)
    matches = list(heading_pattern.finditer(body_text))

    if not matches:
        # No headings - treat whole body as one section
        section_heading = part_title or "(no heading)"
        section_level = 2
        section_path = part_title if part_title else "(no heading)"

        sentences_text = split_into_sentences(body_text)
        for seq, sent_text in enumerate(sentences_text, 1):
            evidence_id = generate_evidence_id(
                content_id, part_slug, section_path, section_index, seq
            )
            text_key = generate_text_key(base_path, sent_text)

            sentences.append(
                Sentence(
                    evidence_id=evidence_id,
                    content_id=content_id,
                    base_path=base_path,
                    part=part_slug,
                    section_path=section_path,
                    section_level=section_level,
                    section_index=section_index,
                    seq=seq,
                    text=sent_text,
                    text_key=text_key,
                    source_updated=source_updated,
                )
            )

        section_index += 1
    else:
        # Process each section
        for i, match in enumerate(matches):
            section_heading = match.group(2).strip()
            section_level = len(match.group(1))  # 2 or 3

            # Build section_path
            if part_title:
                section_path = f"{part_title} > {section_heading}"
            else:
                section_path = section_heading

            # Get section text (from this heading to next, or to end)
            start = match.end()
            if i < len(matches) - 1:
                end = matches[i + 1].start()
            else:
                end = len(body_text)

            section_text = body_text[start:end].strip()

            if not section_text:
                continue

            sentences_text = split_into_sentences(section_text)
            for seq, sent_text in enumerate(sentences_text, 1):
                evidence_id = generate_evidence_id(
                    content_id, part_slug, section_path, section_index, seq
                )
                text_key = generate_text_key(base_path, sent_text)

                sentences.append(
                    Sentence(
                        evidence_id=evidence_id,
                        content_id=content_id,
                        base_path=base_path,
                        part=part_slug,
                        section_path=section_path,
                        section_level=section_level,
                        section_index=section_index,
                        seq=seq,
                        text=sent_text,
                        text_key=text_key,
                        source_updated=source_updated,
                    )
                )

            section_index += 1

    return sentences, section_index


def extract_sentences_from_page(page: dict) -> list[Sentence]:
    """
    Extract sentences from one page (guide or standard).

    Args:
        page: Node dict with base_path, content_id, details, etc.

    Returns:
        List of Sentence objects
    """
    content_id = page["content_id"]
    base_path = page["base_path"]
    source_updated = None  # TODO: Extract from page metadata if available

    # Parse details (it's a JSON string)
    details_str = page.get("details")
    if not details_str:
        return []

    try:
        details = json.loads(details_str) if isinstance(details_str, str) else details_str
    except json.JSONDecodeError:
        print(f"  ⚠️  Could not parse details for {base_path}")
        return []

    sentences = []
    section_index = 1

    # Check if it's a guide with parts
    if "parts" in details and details["parts"]:
        # Guide page: process each part
        for part in details["parts"]:
            part_title = part.get("title", "")
            part_slug = part.get("slug", slugify(part_title))

            # Body is an array [govspeak, html] - use govspeak
            body = part.get("body", [])
            if isinstance(body, list) and len(body) > 0:
                govspeak = body[0]
                body_text = (
                    govspeak.get("content", "") if isinstance(govspeak, dict) else str(govspeak)
                )
            else:
                body_text = str(body) if body else ""

            if not body_text:
                continue

            part_sentences, section_index = extract_sections_from_body(
                body_text,
                content_id,
                base_path,
                part_title,
                part_slug,
                section_index,
                source_updated,
            )
            sentences.extend(part_sentences)

    elif "body" in details:
        # Standard page with single body
        body = details["body"]
        if isinstance(body, list) and len(body) > 0:
            govspeak = body[0]
            body_text = govspeak.get("content", "") if isinstance(govspeak, dict) else str(govspeak)
        else:
            body_text = str(body) if body else ""

        if body_text:
            sentences, _ = extract_sections_from_body(
                body_text, content_id, base_path, "", "", section_index, source_updated
            )

    return sentences


def remove_duplicate_sentences_per_page(sentences: list[Sentence]) -> list[Sentence]:
    """Remove duplicate sentences within the same page"""
    seen = {}  # text_key -> first sentence
    unique = []

    for sent in sentences:
        key = (sent.base_path, sent.text_key)
        if key not in seen:
            seen[key] = sent
            unique.append(sent)

    return unique


def extract_sections_from_subgraph(
    subgraph_path: str = "data/having_a_baby_subgraph.json", output_path: str = "data/sentences.csv"
) -> dict:
    """
    Extract sections and sentences from all pages in subgraph.

    Args:
        subgraph_path: Path to subgraph JSON
        output_path: Where to write sentences CSV

    Returns:
        Dict with counts: pages, sections, sentences
    """
    import pandas as pd

    print(f"\n{'=' * 80}")
    print("Stage 0-1: Section Extraction")
    print(f"{'=' * 80}\n")

    # Load subgraph
    with open(subgraph_path) as f:
        subgraph = json.load(f)

    pages = subgraph["nodes"]
    print(f"Loaded {len(pages)} pages from subgraph\n")

    # Extract sentences from all pages
    all_sentences = []
    pages_processed = 0

    for page in pages:
        base_path = page["base_path"]
        print(f"Processing {base_path}")

        sentences = extract_sentences_from_page(page)
        if sentences:
            all_sentences.extend(sentences)
            pages_processed += 1
            print(f"  → {len(sentences)} sentences")

    # Remove duplicates within same page
    print("\nRemoving duplicate sentences within pages...")
    unique_sentences = remove_duplicate_sentences_per_page(all_sentences)
    removed = len(all_sentences) - len(unique_sentences)
    print(f"  Removed {removed} duplicates")

    # Convert to DataFrame
    rows = []
    for sent in unique_sentences:
        rows.append(
            {
                "evidence_id": sent.evidence_id,
                "content_id": sent.content_id,
                "base_path": sent.base_path,
                "part": sent.part,
                "section_path": sent.section_path,
                "section_level": sent.section_level,
                "section_index": sent.section_index,
                "seq": sent.seq,
                "text": sent.text,
                "text_key": sent.text_key,
                "source_updated": sent.source_updated or "",
            }
        )

    df = pd.DataFrame(rows)

    # Count sections
    sections_count = len(df.groupby(["base_path", "section_index"]))

    # Save
    df.to_csv(output_path, index=False)

    print(f"\n{'=' * 80}")
    print("✓ Section extraction complete")
    print(f"{'=' * 80}\n")
    print(f"Pages processed: {pages_processed}")
    print(f"Sections extracted: {sections_count}")
    print(f"Sentences extracted: {len(unique_sentences)}")
    print(f"\nOutput: {output_path}")

    return {
        "pages": pages_processed,
        "sections": sections_count,
        "sentences": len(unique_sentences),
    }
