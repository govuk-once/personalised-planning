"""Run the plan API over synthetic profiles and emit eval-format plans.

    python run_app.py profiles.json truth.json > app_plans.json
    python run_app.py profiles.json truth.json --profile P011 --verbose
    python run_app.py profiles.json truth.json --relevance > app_plans.json

Ground truth scores plans as sets of step numbers from the GOV.UK
step-by-step spine. The API returns free-text steps, so each response has to
be mapped back onto those numbers. That mapping is done by URL: the spine
carries the GOV.UK paths for each step, and the API cites `gov_service_url`
per task. A cited URL that belongs to a spine step means the app covered
that step.

No LLM sits in the step-scoring path above — it would put a
non-deterministic judgement between the app and its score.

--relevance adds a SEPARATE, optional, LLM-judged metric: for each task the
app returned, is it relevant to *this person's own situation*? This is
independent of the spine (a task can be a perfectly good gov.uk page with
no spine step at all, e.g. the vehicle-tax links a driving-age plan can
legitimately include) and independent of the app's own `reasoning` field,
which is never shown to the judge. Because it is LLM-judged, it is reported
separately in results.json, never folded into precision/recall/F1.
"""

import argparse
import datetime
import json
import pathlib
import sys
import urllib.error
import urllib.request

SITUATION = "learning to drive"

RELEVANCE_PROMPT_PATH = pathlib.Path(__file__).parent / "relevance_prompt.md"
RELEVANCE_VERDICTS = {"relevant", "premature", "irrelevant"}

# Verify this against the Bedrock EU inference profiles available in your
# account/region before relying on it -- model IDs shift over time.
DEFAULT_RELEVANCE_MODEL = "eu.anthropic.claude-sonnet-4-5-20250929-v1:0"
DEFAULT_RELEVANCE_REGION = "eu-west-1"


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
    """Build the user_context dict the API (and the relevance judge) sees.

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


def collect_relevance_tasks(response):
    """Pull the task fields the relevance judge is allowed to see.

    Deliberately excludes the plan's own `reasoning` field (the app's
    self-justification) and the spine/truth (this metric is independent of
    both) — only the task content itself goes to the judge.

    Args:
        response: The parsed API response.

    Returns:
        List of dicts with `title`, `summary`, `gov_service_name`, `url`,
        one per task that has a `gov_service_url`, in plan order.
    """
    tasks = []
    for step in (response.get("plan") or {}).get("steps") or []:
        for task in step.get("tasks") or []:
            url = task.get("gov_service_url") or ""
            if not url:
                continue
            tasks.append(
                {
                    "title": task.get("title") or task.get("task_title") or "",
                    "summary": task.get("summary") or "",
                    "gov_service_name": task.get("gov_service_name") or "",
                    "url": url,
                }
            )
    return tasks


def load_relevance_prompt():
    """Read the relevance judge prompt template from its markdown file."""
    return RELEVANCE_PROMPT_PATH.read_text()


def build_relevance_prompt(template, situation, context, tasks):
    """Fill the prompt template for one plan's relevance judgement.

    Args:
        template: Prompt text from `load_relevance_prompt`.
        situation: The life-event string sent to the API.
        context: Dict from `profile_context`.
        tasks: List from `collect_relevance_tasks`.

    Returns:
        Completed prompt string.
    """
    numbered = "\n\n".join(
        f"{i}. {t['title']}\n"
        f"   Service: {t['gov_service_name']}\n"
        f"   Summary: {t['summary']}\n"
        f"   URL: {t['url']}"
        for i, t in enumerate(tasks)
    )
    return template.format(
        situation=situation,
        context=json.dumps(context, sort_keys=True),
        tasks=numbered,
    )


def invoke_bedrock(client, model_id, prompt, max_tokens=2000):
    """Call a Claude model on Bedrock and return its text output.

    Args:
        client: A boto3 `bedrock-runtime` client.
        model_id: Bedrock model or inference-profile ID.
        prompt: Full prompt text.
        max_tokens: Response token cap.

    Returns:
        The model's text response.

    Raises:
        RuntimeError: If the call fails or the response has no text.
    """
    body = json.dumps(
        {
            "anthropic_version": "bedrock-2023-05-31",
            "max_tokens": max_tokens,
            "temperature": 0,
            "messages": [{"role": "user", "content": prompt}],
        }
    )
    try:
        response = client.invoke_model(modelId=model_id, body=body)
        payload = json.loads(response["body"].read())
        chunks = [
            b["text"] for b in payload.get("content", []) if b.get("type") == "text"
        ]
        if not chunks:
            raise RuntimeError("no text content in Bedrock response")
        return "".join(chunks)
    except Exception as exc:  # noqa: BLE001 - surface any Bedrock/network error uniformly
        raise RuntimeError(f"Bedrock call failed: {exc}") from exc


def parse_relevance_response(text, n_tasks):
    """Parse the judge's JSON array, tolerating stray code fences.

    Any task the model didn't return a valid verdict for is marked
    "unjudged" rather than silently dropped or guessed at.

    Args:
        text: Raw model output.
        n_tasks: Expected number of tasks, for filling gaps.

    Returns:
        List of length `n_tasks` with `verdict` and `rationale` per index.
    """
    cleaned = text.strip()
    if cleaned.startswith("```"):
        cleaned = cleaned.strip("`")
        cleaned = cleaned.split("\n", 1)[1] if "\n" in cleaned else cleaned
    by_index = {}
    try:
        parsed = json.loads(cleaned)
        for item in parsed:
            i = item.get("index")
            verdict = item.get("verdict")
            if isinstance(i, int) and verdict in RELEVANCE_VERDICTS:
                by_index[i] = {
                    "verdict": verdict,
                    "rationale": item.get("rationale", ""),
                }
    except (json.JSONDecodeError, TypeError, AttributeError):
        pass
    return [
        by_index.get(
            i, {"verdict": "unjudged", "rationale": "could not parse judge output"}
        )
        for i in range(n_tasks)
    ]


def judge_plan_relevance(client, model_id, prompt_template, situation, context, tasks):
    """Run the relevance judge over one plan's tasks.

    Args:
        client: A boto3 `bedrock-runtime` client.
        model_id: Bedrock model or inference-profile ID.
        prompt_template: Prompt text from `load_relevance_prompt`.
        situation: The life-event string sent to the API.
        context: Dict from `profile_context`.
        tasks: List from `collect_relevance_tasks`.

    Returns:
        List of dicts merging each task with its verdict and rationale.
    """
    if not tasks:
        return []
    prompt = build_relevance_prompt(prompt_template, situation, context, tasks)
    text = invoke_bedrock(client, model_id, prompt)
    verdicts = parse_relevance_response(text, len(tasks))
    return [{**task, **verdict} for task, verdict in zip(tasks, verdicts, strict=True)]


def aggregate_relevance(per_profile):
    """Roll per-task verdicts up into the two headline relevance metrics.

    Pooled across all judged tasks (not averaged per-profile-then-across),
    matching how precision/recall are pooled via set arithmetic elsewhere
    in this project.

    Args:
        per_profile: List of {"profile_id": ..., "tasks": [...]} records.

    Returns:
        Dict with counts and the two aggregate ratios. Ratios are None if
        no tasks were judged.
    """
    counts = {"relevant": 0, "premature": 0, "irrelevant": 0, "unjudged": 0}
    for record in per_profile:
        for task in record["tasks"]:
            counts[task["verdict"]] = counts.get(task["verdict"], 0) + 1
    judged = counts["relevant"] + counts["premature"] + counts["irrelevant"]
    return {
        "counts": counts,
        "tasks_judged": judged,
        "tasks_unjudged": counts["unjudged"],
        "relevant_only": (counts["relevant"] / judged) if judged else None,
        "relevant_or_premature": (
            (counts["relevant"] + counts["premature"]) / judged if judged else None
        ),
    }


def main(argv=None):
    """Entry point."""
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("profiles")
    ap.add_argument("truth")
    ap.add_argument("--endpoint", default="http://localhost:8000/plan")
    ap.add_argument("--profile", help="run a single profile id, for testing")
    ap.add_argument("--raw", help="also save full API responses here")
    ap.add_argument("--verbose", action="store_true")
    ap.add_argument(
        "--relevance",
        action="store_true",
        help="judge task relevance via Bedrock (EU) and write results.json",
    )
    ap.add_argument("--relevance-model", default=DEFAULT_RELEVANCE_MODEL)
    ap.add_argument("--relevance-region", default=DEFAULT_RELEVANCE_REGION)
    ap.add_argument("--results-out", default="results.json")
    args = ap.parse_args(argv)

    sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
    from truth import score as score_plan

    profiles, truth = load(args.profiles), load(args.truth)
    # One index per guide: step numbers are per-guide, so a single merged index
    # would conflate "step 3 of guide A" with "step 3 of guide B".
    guide_indexes = {path: url_index(spine) for path, spine in truth["spines"].items()}
    by_key = {(t["profile_id"], t["step_by_step"]): t for t in truth["truths"]}

    bedrock, prompt_template = None, None
    if args.relevance:
        import boto3  # deferred: only needed for this optional path

        bedrock = boto3.client("bedrock-runtime", region_name=args.relevance_region)
        prompt_template = load_relevance_prompt()

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
    relevance_records, relevance_failures = [], []
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

        if args.relevance:
            tasks = collect_relevance_tasks(response)
            try:
                judged = judge_plan_relevance(
                    bedrock,
                    args.relevance_model,
                    prompt_template,
                    SITUATION,
                    context,
                    tasks,
                )
                relevance_records.append({"profile_id": profile["id"], "tasks": judged})
            except RuntimeError as exc:
                relevance_failures.append(f"{profile['id']}: {exc}")

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
    for f in relevance_failures:
        print(f"relevance judging failed {f}", file=sys.stderr)

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

    if args.relevance:
        aggregate = aggregate_relevance(relevance_records)
        results["relevance"] = {
            "model": args.relevance_model,
            "region": args.relevance_region,
            "note": (
                "LLM-judged, not deterministic like precision/recall/F1. "
                "Report alongside those metrics, never averaged into them."
            ),
            "profiles_judged": len(relevance_records),
            "profiles_failed": len(relevance_failures),
            "aggregate": {
                "relevant_only": aggregate["relevant_only"],
                "relevant_or_premature": aggregate["relevant_or_premature"],
                "counts": aggregate["counts"],
            },
            "per_profile": relevance_records,
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
