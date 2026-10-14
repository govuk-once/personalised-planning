"""Two-knob (G, N) averaging and results.json assembly.

Averaging contract (as agreed with the user):
- Relevance: average the N judge repeats within each plan first, then average
  across the plans. Plans with no scoreable result are left out.
- Consistency: service stability is computed from the plans (no judge); the
  holistic score is the mean over N repeats, each covering all G plans in one call.
- Overall aggregate = mean of per-profile scores.
"""

import datetime
import statistics

from metrics.services import plan_services


def _mean(values: list) -> float | None:
    """Mean of non-None numeric values, or None if no valid values."""
    vals = [v for v in values if v is not None]
    return statistics.mean(vals) if vals else None


def _relevant_fraction(judged_tasks: list[dict]) -> float | None:
    """Fraction of judged tasks with verdict 'relevant' or 'premature'.

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
    return sum(
        1 for t in scored if t.get("verdict") in ("relevant", "premature")
    ) / len(scored)


def _services_by_plan(generations: list[dict]) -> list[list[dict]]:
    """The distinct services each plan recommends, in plan order."""
    return [list(plan_services(g).values()) for g in generations]


def _services_not_in_every_plan(generations: list[dict]) -> list[dict]:
    """Services recommended by some plans but not all, with 1-based plan numbers."""
    per_plan = [plan_services(g) for g in generations]
    first_seen: dict[str, dict] = {}
    for services in per_plan:
        for key, svc in services.items():
            first_seen.setdefault(key, svc)
    missing = []
    for key, svc in first_seen.items():
        present = [i + 1 for i, services in enumerate(per_plan) if key in services]
        if len(present) < len(per_plan):
            missing.append({**svc, "present_in_plans": present})
    return missing


def compute_results(
    profiles: list[dict],
    generations_by_profile: dict[str, list[dict]],
    consistency_scores: dict[str, list[dict]],
    relevance_scores: dict[str, list[list[list[dict]]]],
    config: dict,
    failures: dict[str, str],
) -> dict:
    """Assemble the final results dict for writing to results.json.

    Args:
        profiles: All profile records that were processed.
        generations_by_profile: ``{profile_id: [generation, ...]}``. Profiles with
            no plans at all are absent.
        consistency_scores: ``{profile_id: [score_dict, ...] * N}``.
            One score dict per repeat (covers all G plans together).
        relevance_scores: ``{profile_id: [[task_list, ...] * G] * N}``.
            Outer list = N repeats; inner list = judged tasks per generation.
        config: The run configuration dict (G, N, models, etc.).
        failures: ``{profile_id: last_error}`` for profiles that produced no plans.

    Returns:
        A results dict ready to be JSON-serialised.
    """
    cons_per = {}
    rel_per = {}

    for profile in profiles:
        pid = profile.get("id", "")
        if pid not in generations_by_profile:
            continue

        # --- Consistency: mean over N repeats ---
        c_repeats = consistency_scores.get(pid, [])
        c_judged = [r for r in c_repeats if r.get("status") == "judged"]
        skipped_note = next(
            (r.get("note") for r in c_repeats if r.get("status") == "skipped"), None
        )
        plans = generations_by_profile[pid]
        cons_per[pid] = {
            "service_stability": _mean([r.get("service_stability") for r in c_judged]),
            "holistic": _mean([r.get("holistic") for r in c_judged]),
            "reasons": [r.get("reasons") for r in c_judged],
            "services_by_plan": _services_by_plan(plans),
            "services_not_in_every_plan": _services_not_in_every_plan(plans),
            "note": skipped_note,
        }

        # --- Relevance: mean over N repeats within each plan, then over plans ---
        r_repeats = relevance_scores.get(pid, [])
        all_tasks = [
            {
                "repeat": n + 1,
                "plan": g + 1,
                "title": t.get("title"),
                "gov_service_name": t.get("gov_service_name"),
                "url": t.get("url"),
                "verdict": t.get("verdict"),
                "rationale": t.get("rationale"),
            }
            for n, repeat in enumerate(r_repeats)
            for g, tasks in enumerate(repeat)
            for t in tasks
        ]
        n_plans = max((len(repeat) for repeat in r_repeats), default=0)
        scores_by_plan = [
            _mean(
                [
                    _relevant_fraction(repeat[g])
                    for repeat in r_repeats
                    if g < len(repeat)
                ]
            )
            for g in range(n_plans)
        ]
        plan_scores = [s for s in scores_by_plan if s is not None]
        rel_per[pid] = {
            "score": _mean(scores_by_plan),
            "scores_by_plan": scores_by_plan,
            "min": min(plan_scores, default=None),
            "max": max(plan_scores, default=None),
            "tasks": all_tasks,
        }

    plans_per_profile = {
        pid: len(plans) for pid, plans in generations_by_profile.items()
    }
    requested_plans = config.get("G")

    return {
        "generated_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "config": config,
        "coverage": {
            "profiles_requested": len(profiles),
            "profiles_scored": len(generations_by_profile),
            "skipped_profiles": [
                {"id": pid, "error": error} for pid, error in failures.items()
            ],
            "plans_requested_per_profile": requested_plans,
            "plans_per_profile": plans_per_profile,
            "profiles_short": [
                pid for pid, n in plans_per_profile.items() if n < requested_plans
            ],
        },
        "consistency": {
            "note": (
                "service_stability is computed from the plans with no judge: the "
                "mean pairwise Jaccard overlap of the services (by URL) each plan "
                "recommends, so it does not change with G. holistic is LLM-judged "
                "via DeepEval GEval over all G plans at once, so compare it only "
                "between runs with the same G. Per-profile holistic = mean of N "
                "judge repeats. Aggregate = mean of per-profile scores. "
                "services_not_in_every_plan is also computed from the plans; plan "
                "numbers are 1-based."
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
                "A plan's score for one repeat = fraction of its tasks judged "
                "'relevant' or 'premature'. scores_by_plan is each plan's score "
                "meaned over the N repeats, in plan order; per-profile score = mean "
                "of scores_by_plan (plans with no scoreable result are left out); "
                "min and max are the lowest and highest plan scores, showing how "
                "much a profile's plans differ. "
                "Aggregate = mean of per-profile scores (not a pooled task ratio). "
                "Each task lists its verdict and the judge's rationale; repeat and "
                "plan numbers are 1-based."
            ),
            "aggregate": _mean([v["score"] for v in rel_per.values()]),
            "per_profile": {
                pid: {
                    "score": v["score"],
                    "scores_by_plan": v["scores_by_plan"],
                    "min": v["min"],
                    "max": v["max"],
                    "tasks": v["tasks"],
                }
                for pid, v in rel_per.items()
            },
        },
    }
