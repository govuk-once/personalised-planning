"""Two-knob (G, N) averaging and results.json assembly.

Averaging contract (as agreed with the user):
- Per-profile score = mean over G plans × N judge repeats (faithfulness/relevance)
  or mean over N repeats (consistency, which already covers all G plans in one call).
- Overall aggregate = mean of per-profile scores.

This differs from ``run_app.py``'s pooled relevance ratio (which pools all tasks
before dividing). Both approaches are noted in the per-metric ``note`` field so
the numbers are not silently compared across tools.
"""

import datetime
import statistics


def _mean(values: list) -> float | None:
    """Mean of non-None numeric values, or None if no valid values."""
    vals = [v for v in values if v is not None]
    return statistics.mean(vals) if vals else None


def _relevant_fraction(judged_tasks: list[dict]) -> float | None:
    """Fraction of judged tasks with verdict 'relevant' (not premature/irrelevant).

    Args:
        judged_tasks: Task dicts with a ``verdict`` key.

    Returns:
        Float in [0, 1] or None if no tasks were judged.
    """
    scored = [
        t
        for t in judged_tasks
        if t.get("verdict") in ("relevant", "premature", "irrelevant")
    ]
    if not scored:
        return None
    return sum(1 for t in scored if t.get("verdict") == "relevant") / len(scored)


def compute_results(
    profiles: list[dict],
    generations_by_profile: dict[str, list[dict]],
    faithfulness_scores: dict[str, list[list[dict]]],
    consistency_scores: dict[str, list[dict]],
    relevance_scores: dict[str, list[list[list[dict]]]],
    config: dict,
) -> dict:
    """Assemble the final results dict for writing to results.json.

    Args:
        profiles: All profile records that were processed.
        generations_by_profile: ``{profile_id: [generation, ...]}``.
        faithfulness_scores: ``{profile_id: [[score_dict, ...] * G] * N}``.
            Outer list = N repeats; inner list = one score per G generation.
        consistency_scores: ``{profile_id: [score_dict, ...] * N}``.
            One score dict per repeat (covers all G plans together).
        relevance_scores: ``{profile_id: [[task_list, ...] * G] * N}``.
            Outer list = N repeats; inner list = judged tasks per generation.
        config: The run configuration dict (G, N, models, etc.).

    Returns:
        A results dict ready to be JSON-serialised.
    """
    faith_per = {}
    cons_per = {}
    rel_per = {}

    for profile in profiles:
        pid = profile.get("id", "")
        if pid not in generations_by_profile:
            continue

        # --- Faithfulness: mean over G plans × N repeats ---
        f_repeats = faithfulness_scores.get(pid, [])
        f_vals = [
            s.get("score")
            for repeat in f_repeats
            for s in repeat
            if s.get("status") == "judged"
        ]
        n_unjudged = sum(
            1 for repeat in f_repeats for s in repeat if s.get("status") == "unjudged"
        )
        faith_per[pid] = {
            "score": _mean(f_vals),
            "n_judged": len(f_vals),
            "n_unjudged": n_unjudged,
        }

        # --- Consistency: mean over N repeats ---
        c_repeats = consistency_scores.get(pid, [])
        c_judged = [r for r in c_repeats if r.get("status") == "judged"]
        skipped_note = next(
            (r.get("note") for r in c_repeats if r.get("status") == "skipped"), None
        )
        cons_per[pid] = {
            "service_stability": _mean([r.get("service_stability") for r in c_judged]),
            "holistic": _mean([r.get("holistic") for r in c_judged]),
            "note": skipped_note,
        }

        # --- Relevance: mean relevant-fraction over G plans × N repeats ---
        r_repeats = relevance_scores.get(pid, [])
        r_vals = [_relevant_fraction(tasks) for repeat in r_repeats for tasks in repeat]
        all_tasks = [t for repeat in r_repeats for tasks in repeat for t in tasks]
        rel_per[pid] = {
            "score": _mean(r_vals),
            "tasks": all_tasks,
        }

    return {
        "generated_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "config": config,
        "faithfulness": {
            "note": (
                "LLM-judged via DeepEval FaithfulnessMetric. "
                "Per-profile score = mean over G plans x N judge repeats. "
                "Aggregate = mean of per-profile scores."
            ),
            "aggregate": _mean([v["score"] for v in faith_per.values()]),
            "per_profile": faith_per,
        },
        "consistency": {
            "note": (
                "LLM-judged via DeepEval GEval (two dimensions). "
                "Per-profile score = mean of N judge repeats over all G plans. "
                "Aggregate = mean of per-profile scores."
            ),
            "aggregate": {
                "service_stability": _mean(
                    [v["service_stability"] for v in cons_per.values()]
                ),
                "holistic": _mean([v["holistic"] for v in cons_per.values()]),
            },
            "per_profile": cons_per,
        },
        "relevance": {
            "note": (
                "Custom Bedrock judge (same prompt as the original relevance judge). "
                "Per-profile score = fraction of tasks judged 'relevant', "
                "meaned over G plans x N repeats. "
                "Aggregate = mean of per-profile scores. "
                "Unlike run_app.py which pools all tasks before dividing, "
                "this averages per-profile first — values are not directly comparable."
            ),
            "aggregate": _mean([v["score"] for v in rel_per.values()]),
            "per_profile": {pid: {"score": v["score"]} for pid, v in rel_per.items()},
        },
    }
