"""Two-knob (G, N) averaging and results.json assembly.

Averaging contract (as agreed with the user):
- Relevance: average the N judge repeats within each plan first, then average
  across the plans. Plans with no scoreable result are left out.
- Consistency: service stability and order agreement are computed from the
  plans (no judge), as the mean over pairs of plans. modal_plan_share,
  same_plan_pair_share and fact consistency are judged; each is the mean over N
  repeats. Difference severities are counted, never turned into scores.
- Overall aggregate = mean of per-profile scores.
- Spread: judged scores report min/max/sd across the N repeats; pairwise
  computed scores report min/max across pairs of plans.
"""

import datetime
import statistics

from metrics.consistency import SEVERITIES
from metrics.services import (
    field_mismatches,
    pairwise_order_agreement,
    pairwise_service_overlaps,
    plan_services,
)


def _mean(values: list) -> float | None:
    """Mean of non-None numeric values, or None if no valid values."""
    vals = [v for v in values if v is not None]
    return statistics.mean(vals) if vals else None


def _spread(values: list) -> dict:
    """Min, max and sample standard deviation of non-None values.

    ``sd`` is None with fewer than two values; all three are None with none.
    """
    vals = [v for v in values if v is not None]
    return {
        "min": min(vals, default=None),
        "max": max(vals, default=None),
        "sd": statistics.stdev(vals) if len(vals) >= 2 else None,
    }


def _range(values: list) -> dict:
    """Min and max of non-None values."""
    vals = [v for v in values if v is not None]
    return {"min": min(vals, default=None), "max": max(vals, default=None)}


def _count_worst_differences(pairs: list[dict]) -> dict[str, int]:
    """Count judged pairs by their most severe difference, least severe first."""
    counts = dict.fromkeys(("none", *SEVERITIES), 0)
    for pair in pairs:
        if pair.get("status") == "judged":
            counts[pair["worst_difference"]] += 1
    return counts


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
        orders = pairwise_order_agreement(plans)
        modal_by_repeat = [r.get("modal_plan_share") for r in c_judged]
        pair_share_by_repeat = [r.get("same_plan_pair_share") for r in c_judged]
        facts_by_repeat = [r.get("fact_consistency") for r in c_judged]
        cons_per[pid] = {
            "service_stability": _mean(overlaps),
            "service_stability_range": _range(overlaps),
            "order_agreement": _mean(orders),
            "order_agreement_range": _range(orders),
            "modal_plan_share": _mean(modal_by_repeat),
            "modal_plan_share_spread": _spread(modal_by_repeat),
            "same_plan_groups_by_repeat": [r.get("same_plan_groups") for r in c_judged],
            "same_plan_pair_share": _mean(pair_share_by_repeat),
            "same_plan_pair_share_spread": _spread(pair_share_by_repeat),
            "pairs_by_worst_difference": _count_worst_differences(
                [pair for r in c_judged for pair in r.get("pairs", [])]
            ),
            "fact_consistency": _mean(facts_by_repeat),
            "fact_consistency_spread": _spread(facts_by_repeat),
            "field_mismatches": [
                {k: v for k, v in m.items() if k != "key"}
                for m in field_mismatches(plans)
            ],
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
            "repeat_spread": _spread(score_by_repeat),
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
                "Computed from the plans with no judge, as means over pairs of "
                "plans: service_stability = Jaccard overlap of the services (by "
                "URL) each plan recommends; order_agreement = share of shared-"
                "service pairs both plans put in the same order (null if a pair "
                "shares fewer than two services); the *_range fields give the "
                "lowest and highest pair. field_mismatches lists shared services "
                "whose cost or dept differ. LLM-judged, mean of N repeats with "
                "min/max/sd in *_spread: two plans are the same plan when the "
                "judge finds no meaningful difference between them (wording "
                "aside). modal_plan_share = share of plans in the largest set of "
                "the same plan (same_plan_groups_by_repeat lists the sets), i.e. "
                "how often the user gets the most common plan; "
                "same_plan_pair_share = share of pairs of plans that are the "
                "same plan. pairs_by_worst_difference counts the judged pairs, "
                "over all N repeats, by their most severe difference. "
                "fact_consistency = share of shared services with no judged "
                "contradiction and no field mismatch. Fewer plans give noisier "
                "scores. Aggregate = mean of per-profile scores; aggregate "
                "pairs_by_worst_difference = sum over profiles. Plan and repeat "
                "numbers are 1-based."
            ),
            "aggregate": {
                **{
                    metric: _mean([v[metric] for v in cons_per.values()])
                    for metric in (
                        "modal_plan_share",
                        "same_plan_pair_share",
                        "service_stability",
                        "order_agreement",
                        "fact_consistency",
                    )
                },
                "pairs_by_worst_difference": {
                    label: sum(
                        v["pairs_by_worst_difference"][label] for v in cons_per.values()
                    )
                    for label in ("none", *SEVERITIES)
                },
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
                "much a profile's plans differ; repeat_spread is the min/max/sd "
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
                    "repeat_spread": v["repeat_spread"],
                    "tasks": v["tasks"],
                }
                for pid, v in rel_per.items()
            },
        },
    }
