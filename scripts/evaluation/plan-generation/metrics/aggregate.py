"""Two-knob (G, N) averaging and results.json assembly.

Averaging contract (as agreed with the user):
- Relevance: average the N judge repeats within each plan first, then average
  across the plans. Plans with no scoreable result are left out.
- Consistency: three measures. Service stability is computed from the plans
  (no judge), as the mean over pairs of plans. Fact consistency and structure
  consistency are judged; each is the mean over N repeats.
- Overall aggregate = mean of per-profile scores.
- Spread: every score reports min/max, across the N repeats for judged scores
  and across pairs of plans for service stability.
"""

import datetime
import statistics

from metrics.services import pairwise_service_overlaps, plan_services


def _mean(values: list) -> float | None:
    """Mean of non-None numeric values, or None if no valid values."""
    vals = [v for v in values if v is not None]
    return statistics.mean(vals) if vals else None


def _range(values: list) -> dict:
    """Min and max of non-None values."""
    vals = [v for v in values if v is not None]
    return {"min": min(vals, default=None), "max": max(vals, default=None)}


def _relevant_fraction(judged_tasks: list[dict]) -> float | None:
    """Fraction of judged tasks with verdict 'relevant'.

    Args:
        judged_tasks: Task dicts with a ``verdict`` key.

    Returns:
        Float in [0, 1] or None if no tasks were judged.
    """
    scored = [
        t
        for t in judged_tasks
        if t.get("verdict") in ("relevant", "contradicted", "irrelevant")
    ]
    if not scored:
        return None
    return sum(1 for t in scored if t.get("verdict") == "relevant") / len(scored)


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
    profile_ids: list[str],
    generations_by_profile: dict[str, list[dict]],
    consistency_scores: dict[str, list[dict]],
    relevance_scores: dict[str, list[list[list[dict]]]],
    config: dict,
    failures: dict[str, str],
) -> dict:
    """Assemble the final results dict for writing to results.json.

    Args:
        profile_ids: IDs of every profile that was requested, in order.
        generations_by_profile: ``{profile_id: [generation, ...]}``. Profiles with
            no plans at all are absent.
        consistency_scores: ``{profile_id: [score_dict, ...] * N}``.
            One score dict per repeat from ``score_consistency``.
        relevance_scores: ``{profile_id: [[task_list, ...] * G] * N}``.
            Outer list = N repeats; inner list = judged tasks per generation.
        config: The run configuration dict (G, N, models, etc.).
        failures: ``{profile_id: last_error}`` for profiles that produced no plans.

    Returns:
        A results dict ready to be JSON-serialised.
    """
    cons_per = {}
    rel_per = {}

    for pid in profile_ids:
        if pid not in generations_by_profile:
            continue

        # --- Consistency: computed over pairs of plans; judged, mean over N ---
        c_repeats = consistency_scores.get(pid, [])
        c_judged = [r for r in c_repeats if r.get("status") == "judged"]
        skipped_note = next(
            (r.get("note") for r in c_repeats if r.get("status") == "skipped"), None
        )
        plans = generations_by_profile[pid]
        overlaps = pairwise_service_overlaps(plans)
        structure_by_repeat = [r.get("structure_consistency") for r in c_judged]
        facts_by_repeat = [r.get("fact_consistency") for r in c_judged]
        cons_per[pid] = {
            "service_stability": _mean(overlaps),
            "service_stability_range": _range(overlaps),
            "fact_consistency": _mean(facts_by_repeat),
            "fact_consistency_range": _range(facts_by_repeat),
            "structure_consistency": _mean(structure_by_repeat),
            "structure_consistency_range": _range(structure_by_repeat),
            "pairs": [
                {"repeat": n + 1, **pair}
                for n, r in enumerate(c_judged)
                for pair in r.get("pairs", [])
            ],
            "fact_checks": [
                {"repeat": n + 1, **check}
                for n, r in enumerate(c_judged)
                for check in r.get("fact_checks", [])
            ],
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
        score_by_repeat = [
            _mean([_relevant_fraction(tasks) for tasks in repeat])
            for repeat in r_repeats
        ]
        rel_per[pid] = {
            "score": _mean(scores_by_plan),
            "scores_by_plan": scores_by_plan,
            "min": min(plan_scores, default=None),
            "max": max(plan_scores, default=None),
            "repeat_range": _range(score_by_repeat),
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
            "profiles_requested": len(profile_ids),
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
                "Three measures, each covering something the others do not. "
                "service_stability (no judge) = Jaccard overlap of the services "
                "(by URL) each plan recommends, averaged over pairs of plans; "
                "the range is the lowest and highest pair. LLM-judged, mean of "
                "N repeats with the lowest and highest repeat in *_range: "
                "fact_consistency = share of services in two or more plans whose "
                "facts (cost, department, deadline, requirements and so on) the "
                "judge finds no contradiction in; structure_consistency = share "
                "of pairs of plans with the same steps, in the same order, and "
                "the same plan summary (the judge lists no differences; which "
                "services the steps contain is not compared). Evidence: "
                "services_not_in_every_plan, fact_checks (each contradiction "
                "with plan numbers) and pairs (each pair's listed differences). "
                "Fewer plans give noisier scores. Aggregate = mean of "
                "per-profile scores. Plan and repeat numbers are 1-based."
            ),
            "aggregate": {
                metric: _mean([v[metric] for v in cons_per.values()])
                for metric in (
                    "service_stability",
                    "fact_consistency",
                    "structure_consistency",
                )
            },
            "per_profile": cons_per,
        },
        "relevance": {
            "note": (
                "Custom Bedrock judge. A task is 'relevant', 'contradicted' (a fact "
                "about the person rules it out) or 'irrelevant'. "
                "A plan's score for one repeat = fraction of its tasks judged "
                "'relevant'. scores_by_plan is each plan's score "
                "meaned over the N repeats, in plan order; per-profile score = mean "
                "of scores_by_plan (plans with no scoreable result are left out); "
                "min and max are the lowest and highest plan scores, showing how "
                "much a profile's plans differ; repeat_range is the min/max "
                "of the profile's score across the N judge repeats. "
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
                    "repeat_range": v["repeat_range"],
                    "tasks": v["tasks"],
                }
                for pid, v in rel_per.items()
            },
        },
    }
