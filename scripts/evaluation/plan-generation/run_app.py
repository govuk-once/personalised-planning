"""Run the plan API over synthetic profiles and emit eval-format plans.

    python run_app.py profiles.json truth.json > app_plans.json
    python run_app.py profiles.json truth.json --profile P011 --verbose

Ground truth scores plans as sets of step numbers from the GOV.UK
step-by-step spine. The API returns free-text steps, so each response has to
be mapped back onto those numbers. That mapping is done by URL: the spine
carries the GOV.UK paths for each step, and the API cites `gov_service_url`
per task. A cited URL that belongs to a spine step means the app covered
that step.

No LLM sits in the step-scoring path — it would put a non-deterministic
judgement between the app and its score.

LLM-based metrics (relevance, faithfulness, consistency) are in the
separate metrics harness: python -m metrics.harness
"""

import argparse
import datetime
import json
import pathlib
import sys
import urllib.error
import urllib.request

SITUATION = "learning to drive"


def load(path):
    """Read a JSON file."""
    resolved = pathlib.Path(path).resolve()
    if not resolved.is_file():
        raise ValueError(f"Not a valid file path: {path}")
    return json.loads(resolved.read_text())


def url_index(spine):
    """Map each GOV.UK path in the spine to its step number.

    Args:
        spine: Steps from the ground-truth file.

    Returns:
        Normalised path mapped to step number.
    """
    out = {}
    for step in spine:
        for link in step["links"]:
            path = (link or "").split("?")[0].split("#")[0].rstrip("/")
            path = path.replace("https://www.gov.uk", "").replace(
                "http://www.gov.uk", ""
            )
            if path.startswith("/"):
                out.setdefault(path, step["step"])
    return out


def profile_context(profile):
    """Build the user_context dict the API sees.

    Args:
        profile: A synthetic profile record.

    Returns:
        Dict of readable answers plus numeric age, if present.
    """
    context = dict(profile.get("readable") or {})
    age = (profile.get("numeric") or {}).get("age", {}).get("value")
    if age is not None:
        context["age"] = int(age)
    return context


def call_api(endpoint, context, timeout=120):
    """Send one profile's context to the plan API.

    Args:
        endpoint: Full URL of the /plan endpoint.
        context: Dict built by `profile_context`.
        timeout: Seconds to wait.

    Returns:
        The parsed response body.

    Raises:
        RuntimeError: If the request fails.
    """
    body = json.dumps({"situation": SITUATION, "user_context": context}).encode()
    request = urllib.request.Request(
        endpoint, data=body, headers={"Content-Type": "application/json"}
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return json.loads(response.read().decode())
    except (urllib.error.URLError, OSError, json.JSONDecodeError) as exc:
        raise RuntimeError(f"{type(exc).__name__}: {exc}") from exc


def trace_tasks(response, index):
    """Match every task's URL against the spine, keeping task identity.

    Matching already happens at task granularity — `gov_service_url` lives
    on tasks, not on the app's own step grouping, which is never read here.
    Keeping the trace (rather than collapsing straight to a step set) is
    what lets you see *which* task covered a step, or spot a step covered
    twice, or a task that cites nothing in the spine.

    The score itself still aggregates to steps. Ground truth verdicts were
    reviewed at step granularity — a step's links are representative
    examples, not an exhaustive checklist — so scoring per link would grade
    against a bar nobody actually approved.

    Args:
        response: The parsed API response.
        index: Path-to-step map from `url_index`.

    Returns:
        One record per task with a `gov_service_url`: task title, url, and
        the spine step it matched (None if it matched nothing).
    """
    trace = []
    for step in (response.get("plan") or {}).get("steps") or []:
        for task in step.get("tasks") or []:
            raw = task.get("gov_service_url") or ""
            if not raw:
                continue
            path = raw.split("?")[0].split("#")[0].rstrip("/")
            path = path.replace("https://www.gov.uk", "").replace(
                "http://www.gov.uk", ""
            )
            trace.append(
                {"task": task.get("task_title"), "url": raw, "step": index.get(path)}
            )
    return trace


def main(argv=None):
    """Entry point."""
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("profiles")
    ap.add_argument("truth")
    ap.add_argument("--endpoint", default="http://localhost:8000/plan")
    ap.add_argument("--profile", help="run a single profile id, for testing")
    ap.add_argument("--raw", help="also save full API responses here")
    ap.add_argument("--verbose", action="store_true")
    ap.add_argument("--results-out", default="results.json")
    args = ap.parse_args(argv)

    sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
    from truth import score as score_plan

    profiles, truth = load(args.profiles), load(args.truth)
    # One index per guide: step numbers are per-guide, so a single merged index
    # would conflate "step 3 of guide A" with "step 3 of guide B".
    guide_indexes = {path: url_index(spine) for path, spine in truth["spines"].items()}
    by_key = {(t["profile_id"], t["step_by_step"]): t for t in truth["truths"]}

    # Only profiles with ground truth are scoreable; guides cover a subset of
    # the cohort, so calling the API for the rest wastes time.
    wanted = {t["profile_id"] for t in truth["truths"]}
    if args.profile:
        wanted &= {args.profile}
    todo = [p for p in profiles["profiles"] if p["id"] in wanted]
    if not todo:
        print("no matching profiles", file=sys.stderr)
        return 1

    plans, raw, failures, unmatched = [], {}, [], set()
    scores = []
    for i, profile in enumerate(todo, 1):
        context = profile_context(profile)
        try:
            response = call_api(args.endpoint, context)
        except RuntimeError as exc:
            failures.append(f"{profile['id']}: {exc}")
            continue
        # Run trace_tasks once per guide; a URL only counts as unmatched if
        # no guide's spine covers it.
        guide_traces = {
            guide_path: trace_tasks(response, guide_index)
            for guide_path, guide_index in guide_indexes.items()
        }
        all_matched = {
            t["url"] for tr in guide_traces.values() for t in tr if t["step"]
        }
        all_cited = {t["url"] for tr in guide_traces.values() for t in tr}
        unmatched.update(all_cited - all_matched)

        for guide_path, trace in guide_traces.items():
            steps = sorted({t["step"] for t in trace if t["step"]})
            plan_record = {
                "profile_id": profile["id"],
                "step_by_step": guide_path,
                "steps": steps,
            }
            plans.append(plan_record)
            truth_entry = by_key.get((profile["id"], guide_path))
            if truth_entry:
                s = score_plan(plan_record, truth_entry)
                s["step_by_step"] = guide_path
                scores.append(s)

        raw[profile["id"]] = {"response": response, "guide_traces": guide_traces}
        if args.verbose:
            for guide_path, trace in guide_traces.items():
                for t in trace:
                    where = f"step {t['step']}" if t["step"] else "NO MATCH"
                    print(
                        f"  {profile['id']} [{guide_path}]: [{where}] {t['task']} -> {t['url']}",
                        file=sys.stderr,
                    )

        print(f"{i}/{len(todo)}", end="\r", file=sys.stderr)

    for f in failures:
        print(f"failed {f}", file=sys.stderr)
    if unmatched:
        # Worth watching: a URL the spine does not know is either a step the
        # guide has no equivalent for, or a citation that will never score.
        print(
            f"{len(unmatched)} cited url(s) matched no spine step, e.g. "
            f"{sorted(unmatched)[:3]}",
            file=sys.stderr,
        )
    empty = sum(1 for p in plans if not p["steps"])
    if empty:
        print(f"warning: {empty} plan(s) matched no steps at all", file=sys.stderr)

    if args.raw:
        resolved_raw = pathlib.Path(args.raw).resolve()
        if not resolved_raw.parent.is_dir():
            raise ValueError(f"Not a valid output path: {args.raw}")
        resolved_raw.write_text(json.dumps(raw, indent=2))

    n = len(scores)
    if n:
        agg_tp = agg_got = agg_want = 0
        plans_by_key = {(pl["profile_id"], pl["step_by_step"]): pl for pl in plans}
        for s in scores:
            truth_rec = by_key.get((s["profile_id"], s["step_by_step"]))
            if truth_rec:
                want = {
                    v["step"]
                    for v in truth_rec["verdicts"]
                    if v["verdict"] == "required"
                }
                got_steps = set(
                    plans_by_key[(s["profile_id"], s["step_by_step"])]["steps"]
                )
                agg_tp += len(want & got_steps)
                agg_got += len(got_steps)
                agg_want += len(want)
        agg_p = round(agg_tp / agg_got, 3) if agg_got else 0.0
        agg_r = round(agg_tp / agg_want, 3) if agg_want else 0.0
        agg_f1 = round(2 * agg_p * agg_r / (agg_p + agg_r), 3) if agg_p + agg_r else 0.0
        scoring_block = {
            "aggregate": {
                "precision": agg_p,
                "recall": agg_r,
                "f1": agg_f1,
                "mean_f1": round(sum(s["f1"] for s in scores) / n, 3),
                "profiles_scored": n,
                "perfect": sum(
                    1 for s in scores if s["f1"] >= 1.0 and not s["blocked_but_present"]
                ),
                "presented_a_blocked_step": sum(
                    1 for s in scores if s["blocked_but_present"]
                ),
                "missed_a_required_step": sum(1 for s in scores if s["missing"]),
            },
            "per_profile": scores,
        }
    else:
        scoring_block = {"aggregate": {}, "per_profile": []}

    results = {
        "generated_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "scoring": scoring_block,
    }

    resolved_results_out = pathlib.Path(args.results_out).resolve()
    if not resolved_results_out.parent.is_dir():
        raise ValueError(f"Not a valid output path: {args.results_out}")
    resolved_results_out.write_text(json.dumps(results, indent=2))
    print(f"wrote results to {args.results_out}", file=sys.stderr)

    print(json.dumps({"plans": plans}, indent=2))
    print(f"wrote {len(plans)} plans, {len(failures)} failed", file=sys.stderr)
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
