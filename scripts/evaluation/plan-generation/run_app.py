"""Run the hosted planner agent over synthetic profiles and emit eval-format plans.

    python run_app.py profiles.json truth.json > app_plans.json
    python run_app.py profiles.json truth.json --profile P011 --verbose
    python run_app.py profiles.json truth.json --from-raw raw.json > app_plans.json

The agent is invoked in AgentCore Runtime, as the backend Worker does. Pass its
ARN with --agent-runtime-arn or set AGENT_RUNTIME_ARN, and run with AWS
credentials that allow bedrock-agentcore:InvokeAgentRuntime.

Ground truth scores plans as sets of step numbers from the GOV.UK
step-by-step spine. The agent returns free-text steps, so each response has to
be mapped back onto those numbers. That mapping is done by URL: the spine
carries the GOV.UK paths for each step, and the agent cites `gov_service_url`
per task. A cited URL that belongs to a spine step means the app covered
that step. A sub-page counts as its parent page. When several steps link the
same page, the task's title decides between them, using each step's
`match_terms` (see `match_task`).

--from-raw re-matches and re-scores responses saved with --raw, so a change to
matching or to the answer key needs no new agent calls.

No LLM sits in the step-scoring path — it would put a non-deterministic
judgement between the app and its score.

LLM-based metrics (relevance, consistency) are in the separate metrics
harness: python -m metrics.harness generate|score
"""

import argparse
import collections
import datetime
import hashlib
import json
import os
import pathlib
import re
import sys
import uuid
import zoneinfo

import boto3
from botocore.config import Config
from botocore.exceptions import BotoCoreError, ClientError


def load(path):
    """Read a JSON file."""
    resolved = pathlib.Path(path).resolve()
    if not resolved.is_file():
        raise ValueError(f"Not a valid file path: {path}")
    return json.loads(resolved.read_text())


def _path(url):
    """A GOV.UK URL as a bare path; other URLs are returned without query or anchor."""
    path = (url or "").split("?")[0].split("#")[0].rstrip("/")
    return path.replace("https://www.gov.uk", "").replace("http://www.gov.uk", "")


def url_index(spine):
    """Index a spine for matching tasks to steps.

    Args:
        spine: Steps from the ground-truth file. A step may carry
            `match_terms`: words or phrases that identify a task for that
            step when its URL is shared with other steps.

    Returns:
        A dict with `paths` (normalised path mapped to every step linking it,
        in step order) and `terms` (step number mapped to compiled patterns).
    """
    paths, terms = {}, {}
    for step in spine:
        for link in step["links"]:
            path = _path(link)
            if path.startswith("/") and step["step"] not in paths.setdefault(path, []):
                paths[path].append(step["step"])
        terms[step["step"]] = [
            re.compile(r"(?<!\w)" + re.escape(t) + r"(?!\w)", re.IGNORECASE)
            for t in step.get("match_terms") or []
        ]
    return {"paths": paths, "terms": terms}


def match_task(task, index):
    """The spine steps one task covers, and how that was decided.

    A URL linked from one step decides it. A sub-page counts as its parent
    page. A URL linked from several steps credits each of those steps whose
    `match_terms` appear in the task title (a task can do more than one stage,
    such as "check and claim"); if none appear, it credits the earliest of
    them, as matching on URL alone would.

    Args:
        task: A task from the agent's plan.
        index: From `url_index`.

    Returns:
        A (steps, how) pair: a sorted list of step numbers (empty if the task
        cites nothing in the spine) and one of "url", "terms", "fallback" or
        "unmatched".
    """
    path = _path(task.get("gov_service_url"))
    candidates = index["paths"].get(path)
    if not candidates and path.count("/") > 1:
        candidates = index["paths"].get(path.rsplit("/", 1)[0])
    if not candidates:
        return [], "unmatched"
    if len(candidates) == 1:
        return list(candidates), "url"
    title = task.get("title") or task.get("task_title") or ""
    hits = [
        s for s in candidates if any(p.search(title) for p in index["terms"].get(s, []))
    ]
    if hits:
        return sorted(hits), "terms"
    return [min(candidates)], "fallback"


def today_london():
    """Today's date as the backend Worker formats it, e.g. "13 October 2026"."""
    now = datetime.datetime.now(zoneinfo.ZoneInfo("Europe/London"))
    return f"{now.day} {now:%B} {now.year}"


def profile_situation(profile):
    """The situation sentence the agent sees for a profile.

    Args:
        profile: A synthetic profile record.

    Returns:
        The profile's `situation`, as added by `situations.py`.

    Raises:
        ValueError: If the profile has no situation.
    """
    situation = (profile.get("situation") or "").strip()
    if not situation:
        raise ValueError(
            f"profile {profile.get('id', '?')} has no situation; "
            "run situations.py on the profiles file"
        )
    return situation


def profile_context(profile):
    """Build the user_context dict the agent sees.

    Mirrors the backend Worker, which adds today's date: without it the
    planner works out deadlines from its training cutoff. Answers go in as
    the profile's question ids and option codes, like the short keys and values
    the conversation agent collects in production.

    Args:
        profile: A synthetic profile record.

    Returns:
        Dict of today's date, answer codes, and numeric age if present.
    """
    context = {"today": today_london(), **(profile.get("answers") or {})}
    age = (profile.get("numeric") or {}).get("age", {}).get("value")
    if age is not None:
        context["age"] = int(age)
    return context


def make_agent_client(runtime_arn, timeout=300):
    """Build a bedrock-agentcore client for the region of the planner runtime.

    Args:
        runtime_arn: ARN of the deployed planner runtime.
        timeout: Seconds to wait for a plan. A planner run takes minutes, well
            past boto3's 60 second default. Requests are not retried.

    Returns:
        A boto3 ``bedrock-agentcore`` client.

    Raises:
        ValueError: If the ARN is not an AgentCore ARN.
    """
    parts = runtime_arn.split(":")
    if len(parts) < 6 or parts[2] != "bedrock-agentcore" or not parts[3]:
        raise ValueError(f"Not an AgentCore runtime ARN: {runtime_arn}")
    return boto3.client(
        "bedrock-agentcore",
        region_name=parts[3],
        config=Config(read_timeout=timeout, retries={"max_attempts": 0}),
    )


def call_api(client, runtime_arn, situation, context):
    """Send one profile's situation and context to the hosted planner agent.

    Args:
        client: Client from `make_agent_client`.
        runtime_arn: ARN of the deployed planner runtime.
        situation: Sentence from `profile_situation`.
        context: Dict built by `profile_context`.

    Returns:
        The agent's output dict, with ``plan``, ``agent_help`` and ``timestamp``.

    Raises:
        RuntimeError: If the invocation fails or the reply has no output.
    """
    body = json.dumps({"situation": situation, "user_context": context}).encode()
    try:
        reply = client.invoke_agent_runtime(
            agentRuntimeArn=runtime_arn,
            runtimeSessionId=str(uuid.uuid4()),
            qualifier=os.environ.get("AGENT_ENDPOINT_NAME") or "DEFAULT",
            contentType="application/json",
            accept="application/json",
            payload=body,
        )
        parsed = json.loads(reply["response"].read().decode())
    except (BotoCoreError, ClientError, OSError, json.JSONDecodeError) as exc:
        raise RuntimeError(f"{type(exc).__name__}: {exc}") from exc

    output = parsed.get("output") if isinstance(parsed, dict) else None
    if not isinstance(output, dict):
        raise RuntimeError(f"unexpected agent reply: {str(parsed)[:200]}")
    return output


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
        response: The agent's output dict from `call_api`.
        index: From `url_index`.

    Returns:
        One record per task with a `gov_service_url`: task title, url, the
        spine steps it matched (empty if none) and how they were decided
        (see `match_task`).
    """
    trace = []
    for step in (response.get("plan") or {}).get("steps") or []:
        for task in step.get("tasks") or []:
            raw = task.get("gov_service_url") or ""
            if not raw:
                continue
            steps, how = match_task(task, index)
            trace.append(
                {
                    "task": task.get("title") or task.get("task_title"),
                    "url": raw,
                    "steps": steps,
                    "how": how,
                }
            )
    return trace


PLANS_KIND = "plan-generations"  # the metrics harness's plans file format


def _parse_args(argv):
    """Command-line options."""
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("profiles")
    ap.add_argument("truth")
    ap.add_argument(
        "--agent-runtime-arn",
        default=os.environ.get("AGENT_RUNTIME_ARN"),
        help="ARN of the hosted planner runtime (default: $AGENT_RUNTIME_ARN)",
    )
    ap.add_argument("--profile", help="run a single profile id, for testing")
    ap.add_argument("--raw", help="also save full agent responses here")
    ap.add_argument("--verbose", action="store_true")
    ap.add_argument("--results-out", default="results.json")
    source = ap.add_mutually_exclusive_group()
    source.add_argument(
        "--from-raw",
        nargs="+",
        metavar="RAW",
        help="re-match and re-score agent responses saved earlier with --raw, "
        "without calling the agent (no ARN or credentials needed)",
    )
    source.add_argument(
        "--from-plans",
        metavar="PLANS",
        help="score a plans file from `metrics.harness generate` (every plan in "
        "it), without calling the agent (no ARN or credentials needed)",
    )
    return ap.parse_args(argv)


def _load_plans_file(path):
    """A `metrics.harness generate` plans file, checked for its format."""
    doc = load(path)
    if not isinstance(doc, dict) or doc.get("kind") != PLANS_KIND:
        raise ValueError(f"{path}: not a metrics.harness plans file")
    return doc


def _from_agent(client, runtime_arn, todo, failures):
    """(profile, plan number, response) for each profile, calling the agent."""
    for profile in todo:
        try:
            situation = profile_situation(profile)
            response = call_api(
                client, runtime_arn, situation, profile_context(profile)
            )
        except RuntimeError as exc:
            failures.append(f"{profile['id']}: {exc}")
            continue
        yield profile, 1, response


def _from_raw(saved, todo):
    """(profile, plan number, response) for each profile saved with --raw."""
    for profile in todo:
        yield profile, 1, saved[profile["id"]]["response"]


def _from_plans(plans_doc, todo):
    """(profile, plan number, response) for every plan in a harness plans file."""
    for profile in todo:
        for n, gen in enumerate(plans_doc["plans"][profile["id"]], 1):
            yield profile, n, {"plan": gen.get("plan")}


def _step_detail(spine, truth_entry, trace):
    """Each step's verdict, whether the plan covered it, and the tasks that did."""
    verdict = {v["step"]: v["verdict"] for v in truth_entry["verdicts"]}
    detail = []
    for step in spine:
        tasks = [
            {"title": t["task"], "url": t["url"], "how": t["how"]}
            for t in trace
            if step["step"] in t["steps"]
        ]
        detail.append(
            {
                "step": step["step"],
                "verdict": verdict.get(step["step"]),
                "covered": bool(tasks),
                "tasks": tasks,
            }
        )
    return detail


def _counts(truth_entry, steps):
    """Required, covered and shown step counts, as truth.score uses them."""
    by_verdict = collections.defaultdict(set)
    for v in truth_entry["verdicts"]:
        by_verdict[v["verdict"]].add(v["step"])
    # Optional steps are neutral, as in truth.score: not counted as shown,
    # so they cannot lower precision.
    shown = set(steps) - by_verdict["optional"]
    want = by_verdict["required"]
    return {"required": len(want), "covered": len(want & shown), "shown": len(shown)}


def _score_one(profile, plan_no, response, ctx):
    """Plan records, score rows and the raw trace for one plan."""
    traces = {
        path: trace_tasks(response, index) for path, index in ctx["indexes"].items()
    }
    records, rows = [], []
    for path, trace in traces.items():
        steps = sorted({s for t in trace for s in t["steps"]})
        record = {
            "profile_id": profile["id"],
            "plan": plan_no,
            "step_by_step": path,
            "steps": steps,
        }
        records.append(record)
        truth_entry = ctx["by_key"].get((profile["id"], path))
        if not truth_entry:
            continue
        row = ctx["score"](record, truth_entry)
        row.update(
            {
                "plan": plan_no,
                "step_by_step": path,
                "counts": _counts(truth_entry, steps),
                "step_detail": _step_detail(ctx["spines"][path], truth_entry, trace),
                "unmatched_tasks": [
                    {"title": t["task"], "url": t["url"]}
                    for t in trace
                    if not t["steps"]
                ],
            }
        )
        rows.append(row)
    return records, rows, traces


def _mean(values, weights=None):
    """Plain or weighted mean, rounded; 0.0 for nothing."""
    values = list(values)
    if not values:
        return 0.0
    weights = list(weights) if weights is not None else [1.0] * len(values)
    total = sum(weights)
    return (
        round(sum(v * w for v, w in zip(values, weights, strict=True)) / total, 3)
        if total
        else 0.0
    )


def _aggregate(rows):
    """Pooled precision, recall and F1, plus per-plan means and counts."""
    tp = sum(r["counts"]["covered"] for r in rows)
    got = sum(r["counts"]["shown"] for r in rows)
    want = sum(r["counts"]["required"] for r in rows)
    p = round(tp / got, 3) if got else 0.0
    r = round(tp / want, 3) if want else 0.0
    return {
        "precision": p,
        "recall": r,
        "f1": round(2 * p * r / (p + r), 3) if p + r else 0.0,
        "mean_precision": _mean(x["precision"] for x in rows),
        "mean_recall": _mean(x["recall"] for x in rows),
        "mean_f1": _mean(x["f1"] for x in rows),
        "profiles_scored": len({x["profile_id"] for x in rows}),
        "plans_scored": len(rows),
        "perfect": sum(
            1 for x in rows if x["f1"] >= 1.0 and not x["blocked_but_present"]
        ),
        "presented_a_blocked_step": sum(1 for x in rows if x["blocked_but_present"]),
        "missed_a_required_step": sum(1 for x in rows if x["missing"]),
    }


def _weighted_aggregate(rows, weights):
    """Per-plan scores averaged by profile weight, split across a profile's plans."""
    per_profile = collections.Counter(x["profile_id"] for x in rows)
    w = [weights.get(x["profile_id"], 0.0) / per_profile[x["profile_id"]] for x in rows]
    return {
        "mean_precision": _mean((x["precision"] for x in rows), w),
        "mean_recall": _mean((x["recall"] for x in rows), w),
        "mean_f1": _mean((x["f1"] for x in rows), w),
        "weight_scored": round(sum(w), 3),
    }


def _resolved(path):
    """An absolute path, as `metrics.harness` records them, or None."""
    return str(pathlib.Path(path).resolve()) if path else None


def _config(args, truth_path, plans_doc, rows, weights):
    """What this run scored, so results can be paired and compared later.

    `plans_file` and `plans_generated_at` are recorded as `metrics.harness
    score` records them, so the dashboard can pair plan-quality and harness
    results for the same plans. The agent's ARN is never recorded.
    """
    digest = hashlib.sha256(pathlib.Path(truth_path).read_bytes()).hexdigest()
    plans_per_profile = collections.Counter(x["profile_id"] for x in rows)
    source = "plans" if args.from_plans else "raw" if args.from_raw else "agent"
    resolved = _resolved
    return {
        "source": source,
        "profiles_file": resolved(args.profiles),
        "weights_file": resolved(args.profiles) if weights else None,
        "truth_file": resolved(truth_path),
        "truth_sha256": digest,
        "plans_file": resolved(args.from_plans),
        "plans_generated_at": (plans_doc or {}).get("generated_at"),
        "raw_files": [resolved(p) for p in args.from_raw] if args.from_raw else None,
        "G": max(plans_per_profile.values(), default=0),
        "scored_profile": args.profile,
        "matcher": "url; sub-page as parent; match_terms on task title for shared urls",
    }


def _write_json(path, obj):
    """Write JSON to an existing directory."""
    resolved = pathlib.Path(path).resolve()
    if not resolved.parent.is_dir():
        raise ValueError(f"Not a valid output path: {path}")
    resolved.write_text(json.dumps(obj, indent=2))


def _print_trace(profile_id, plan_no, traces):
    """Per-task matching, for --verbose."""
    for path, trace in traces.items():
        for t in trace:
            where = (
                f"step {','.join(map(str, t['steps']))} ({t['how']})"
                if t["steps"]
                else "NO MATCH"
            )
            print(
                f"  {profile_id}#{plan_no} [{path}]: [{where}] {t['task']} -> {t['url']}",
                file=sys.stderr,
            )


def _report(failures, rows, records):
    """Failures, unmatched citations and empty plans, on stderr."""
    for f in failures:
        print(f"failed {f}", file=sys.stderr)
    unmatched = {t["url"] for r in rows for t in r["unmatched_tasks"]}
    if unmatched:
        # Worth watching: a URL the spine does not know is either a step the
        # guide has no equivalent for, or a citation that will never score.
        print(
            f"{len(unmatched)} cited url(s) matched no spine step, e.g. {sorted(unmatched)[:3]}",
            file=sys.stderr,
        )
    empty = sum(1 for p in records if not p["steps"])
    if empty:
        print(f"warning: {empty} plan(s) matched no steps at all", file=sys.stderr)


def _setup(args):
    """The plan source and, if the agent is called, its client."""
    if args.from_raw:
        saved = {}
        for path in args.from_raw:
            saved.update(load(path))
        return {"saved": saved}, None
    if args.from_plans:
        return {"plans": _load_plans_file(args.from_plans)}, None
    if not args.agent_runtime_arn:
        raise ValueError("AGENT_RUNTIME_ARN is not set (or pass --agent-runtime-arn)")
    return {}, make_agent_client(args.agent_runtime_arn)


def main(argv=None):
    """Entry point."""
    args = _parse_args(argv)
    try:
        source, client = _setup(args)
    except ValueError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1

    sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
    from truth import score as score_plan

    profiles, truth = load(args.profiles), load(args.truth)
    # One index per guide: step numbers are per-guide, so a single merged index
    # would conflate "step 3 of guide A" with "step 3 of guide B".
    ctx = {
        "indexes": {path: url_index(spine) for path, spine in truth["spines"].items()},
        "spines": truth["spines"],
        "by_key": {(t["profile_id"], t["step_by_step"]): t for t in truth["truths"]},
        "score": score_plan,
    }

    # Only profiles with ground truth are scoreable; guides cover a subset of
    # the cohort, so calling the API for the rest wastes time.
    wanted = {t["profile_id"] for t in truth["truths"]}
    if args.profile:
        wanted &= {args.profile}
    if "saved" in source:
        wanted &= set(source["saved"])
    if "plans" in source:
        wanted &= set(source["plans"]["plans"])
    todo = [p for p in profiles["profiles"] if p["id"] in wanted]
    if not todo:
        print("no matching profiles", file=sys.stderr)
        return 1

    failures = []
    if "saved" in source:
        responses = _from_raw(source["saved"], todo)
    elif "plans" in source:
        responses = _from_plans(source["plans"], todo)
    else:
        # Check every situation before the first slow agent call.
        try:
            for p in todo:
                profile_situation(p)
        except ValueError as exc:
            print(f"error: {exc}", file=sys.stderr)
            return 1
        responses = _from_agent(client, args.agent_runtime_arn, todo, failures)

    records, rows, raw = [], [], {}
    for i, (profile, plan_no, response) in enumerate(responses, 1):
        plan_records, plan_rows, traces = _score_one(profile, plan_no, response, ctx)
        records += plan_records
        rows += plan_rows
        if "plans" in source:
            raw.setdefault(profile["id"], {"plans": []})["plans"].append(
                {"plan": plan_no, "guide_traces": traces}
            )
        else:
            raw[profile["id"]] = {"response": response, "guide_traces": traces}
        if args.verbose:
            _print_trace(profile["id"], plan_no, traces)
        print(f"{i} plan(s) scored", end="\r", file=sys.stderr)

    _report(failures, rows, records)
    if args.raw:
        _write_json(args.raw, raw)

    weights = {p["id"]: p["weight"] for p in profiles["profiles"] if "weight" in p}
    scoring = {"aggregate": _aggregate(rows) if rows else {}, "per_profile": rows}
    if weights and rows:
        scoring["weighted_aggregate"] = _weighted_aggregate(rows, weights)
    results = {
        "generated_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "config": _config(args, args.truth, source.get("plans"), rows, weights),
        "steps": {
            path: [
                {
                    "step": s["step"],
                    "title": s["title"],
                    "optional": bool(s.get("optional")),
                }
                for s in spine
            ]
            for path, spine in truth["spines"].items()
        },
        "scoring": scoring,
    }
    _write_json(args.results_out, results)
    print(f"wrote results to {args.results_out}", file=sys.stderr)

    print(json.dumps({"plans": records}, indent=2))
    print(f"wrote {len(records)} plans, {len(failures)} failed", file=sys.stderr)
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
