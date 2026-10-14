r"""Standalone metrics harness: consistency and relevance.

Runs independently of the main pipeline — no truth file, no spine, no F1. Two
steps, so plans are generated once and can be scored many times:

1. ``generate`` calls the hosted planner agent in AgentCore Runtime G times per
   profile and saves the plans to a plans file. Needs AGENT_RUNTIME_ARN (or
   --agent-runtime-arn) and AWS credentials that can invoke the runtime.
2. ``score`` judges a plans file N times per metric and writes results.json.
   Needs EVAL_ANTHROPIC_MODEL (or --judge-model) and Bedrock access, but no agent.

Examples::

    # Generate 3 plans per profile once...
    python -m metrics.harness generate profiles.json -G 3 -o plans.json

    # ...then score them as often as you like, e.g. after changing a prompt
    python -m metrics.harness score plans.json -N 2 --results-out results.json

    # Single profile, relevance only
    python -m metrics.harness score plans.json --profile P013 --metrics relevance

Knobs:
    G   = plan generations per profile (set when generating).
    N   = judge repeats per metric per profile (set when scoring).

Relevance per profile = mean over plans of (mean over N repeats). Consistency
service stability is computed from the plans; holistic is the mean over N repeats.
Overall aggregate = mean of per-profile scores.

A failed plan generation is retried up to --max-attempts times if the error looks
transient (throttling, timeouts, 5xx, an empty reply); permanent errors such as
AccessDenied are not retried. ``generate`` exits 1 if any profile got no plans or
fewer than G; that coverage is carried into results.json by ``score``.
"""

import argparse
import datetime
import json
import os
import pathlib
import sys
import time
import warnings

from botocore.exceptions import (
    ClientError,
    ConnectionError as BotoConnectionError,
    EndpointConnectionError,
    HTTPClientError,
)

_VALID_METRICS = frozenset({"consistency", "relevance"})

_PLANS_KIND = "plan-generations"
_PLANS_VERSION = 1

# Error codes InvokeAgentRuntime can return that are worth retrying.
_TRANSIENT_CODES = frozenset(
    {
        "ThrottlingException",
        "InternalServerException",
        "RetryableConflictException",
        "RuntimeClientError",
    }
)


def _load(path: str):
    """Load and parse a JSON file, exiting with an error message on failure."""
    p = pathlib.Path(path).resolve()
    if not p.is_file():
        sys.exit(f"error: not a file: {path}")
    return json.loads(p.read_text())


def _output_path(path: str) -> pathlib.Path:
    """Resolve an output path, exiting if its directory does not exist."""
    out = pathlib.Path(path).resolve()
    if not out.parent.is_dir():
        sys.exit(f"error: output directory does not exist: {out.parent}")
    return out


def _write_json_atomic(path: pathlib.Path, data: dict) -> None:
    """Write JSON so a crash mid-write never leaves a truncated file."""
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(json.dumps(data, indent=2))
    os.replace(tmp, path)


def _eval_dir_on_path() -> None:
    """Make run_app (a sibling of the metrics package) importable."""
    eval_dir = str(pathlib.Path(__file__).resolve().parents[1])
    if eval_dir not in sys.path:
        sys.path.insert(0, eval_dir)


def _is_transient(exc: RuntimeError) -> bool:
    """Whether a failed agent call is worth retrying.

    Retries throttling, server errors, timeouts, connection errors and replies
    that were not valid. Anything else (access denied, bad request, missing or
    expired credentials, unknown errors) is treated as permanent so it fails at
    once instead of looping.

    Args:
        exc: The RuntimeError raised by ``run_app.call_api``; the underlying
            error is on ``__cause__``.

    Returns:
        True if another attempt might succeed.
    """
    cause = exc.__cause__
    if isinstance(cause, ClientError):
        return cause.response.get("Error", {}).get("Code") in _TRANSIENT_CODES
    if isinstance(
        cause, BotoConnectionError | EndpointConnectionError | HTTPClientError | OSError
    ):
        return True
    # No cause: the agent replied but with no usable output. A bad JSON body is
    # the same kind of failure.
    return cause is None or isinstance(cause, json.JSONDecodeError)


def _generate_one(
    client, runtime_arn: str, context: dict, max_attempts: int
) -> tuple[dict | None, str | None]:
    """Get one plan from the hosted agent, retrying transient failures.

    Waits 5s, 10s, 20s... (capped at 60s) between attempts. Retrying is safe: the
    planner has no side effects and every call uses a fresh session.

    Args:
        client: Client from ``run_app.make_agent_client``.
        runtime_arn: ARN of the deployed planner runtime.
        context: The user_context dict from ``profile_context``.
        max_attempts: Total tries, including the first.

    Returns:
        ``(generation, None)`` on success, or ``(None, last_error)``.
    """
    from run_app import call_api

    error = "no attempts made"
    for attempt in range(1, max_attempts + 1):
        try:
            plan = call_api(client, runtime_arn, context).get("plan")
        except RuntimeError as exc:
            error = str(exc)
            if not _is_transient(exc):
                return None, error
        else:
            if plan:
                return {"plan": plan, "context": context}, None
            error = "no plan in response"

        if attempt < max_attempts:
            wait = min(60, 5 * 2 ** (attempt - 1))
            print(
                f"  attempt {attempt}/{max_attempts} failed ({error}); "
                f"retrying in {wait}s",
                file=sys.stderr,
            )
            time.sleep(wait)
    return None, error


def _short_profiles(plans: dict[str, list], g: int | None) -> list[str]:
    """Profiles that got at least one plan but fewer than G."""
    if not g:
        return []
    return [pid for pid, gens in plans.items() if len(gens) < g]


def _cmd_generate(args: argparse.Namespace) -> int:
    """Generate G plans per profile from the hosted agent and save a plans file."""
    if args.max_attempts < 1:
        sys.exit("error: --max-attempts must be at least 1")
    if args.G < 1:
        sys.exit("error: -G must be at least 1")

    profiles_data = _load(args.profiles)
    all_profiles = (
        profiles_data.get("profiles", [])
        if isinstance(profiles_data, dict)
        else profiles_data
    )
    if args.profile:
        all_profiles = [p for p in all_profiles if p.get("id") == args.profile]
    if not all_profiles:
        sys.exit("error: no matching profiles found")

    _eval_dir_on_path()
    from run_app import SITUATION, make_agent_client, profile_context

    if not args.agent_runtime_arn:
        sys.exit("error: AGENT_RUNTIME_ARN is not set (or pass --agent-runtime-arn)")
    try:
        agent_client = make_agent_client(args.agent_runtime_arn)
    except ValueError as exc:
        sys.exit(f"error: {exc}")

    out_path = _output_path(args.plans_out)
    total = len(all_profiles)
    doc = {
        "kind": _PLANS_KIND,
        "version": _PLANS_VERSION,
        "generated_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "config": {
            "G": args.G,
            "agent_runtime_arn": args.agent_runtime_arn,
            "max_attempts": args.max_attempts,
            "situation": SITUATION,
            "profiles_file": str(pathlib.Path(args.profiles).resolve()),
            "profile": args.profile,
        },
        "profile_ids": [p.get("id", f"profile_{i}") for i, p in enumerate(all_profiles, 1)],
        "plans": {},
        "failures": {},
    }

    for i, (pid, profile) in enumerate(zip(doc["profile_ids"], all_profiles, strict=True), 1):
        print(f"[{i}/{total}] {pid}", file=sys.stderr)
        ctx = profile_context(profile)
        gens = []
        last_error = None
        for g in range(args.G):
            gen, error = _generate_one(
                agent_client, args.agent_runtime_arn, ctx, args.max_attempts
            )
            if gen:
                gens.append(gen)
            else:
                last_error = error
                print(f"  gen {g + 1} failed: {error}", file=sys.stderr)

        if gens:
            doc["plans"][pid] = gens
            if args.verbose:
                print(f"  {pid}: {len(gens)}/{args.G} plans", file=sys.stderr)
        else:
            doc["failures"][pid] = last_error or "no plans generated"
            print(f"  {pid}: all generations failed, skipping", file=sys.stderr)

        # Save after every profile so an interrupted run keeps the work done so far.
        _write_json_atomic(out_path, doc)

    print(f"wrote plans to {args.plans_out}", file=sys.stderr)

    short = _short_profiles(doc["plans"], args.G)
    print(f"generated plans for {len(doc['plans'])}/{total} profiles", file=sys.stderr)
    for pid, error in doc["failures"].items():
        print(f"  skipped {pid}: {error}", file=sys.stderr)
    for pid in short:
        print(f"  short {pid}: {len(doc['plans'][pid])}/{args.G} plans", file=sys.stderr)

    return 1 if doc["failures"] or short else 0


def _cmd_score(args: argparse.Namespace) -> int:
    """Judge a saved plans file N times per metric and write results.json."""
    if args.N < 1:
        sys.exit("error: -N must be at least 1")
    plans_path = pathlib.Path(args.plans).resolve()
    doc = _load(args.plans)
    if (
        not isinstance(doc, dict)
        or doc.get("kind") != _PLANS_KIND
        or doc.get("version") != _PLANS_VERSION
    ):
        sys.exit(
            f"error: {args.plans} is not a plans file "
            f"(expected kind={_PLANS_KIND!r}, version={_PLANS_VERSION}); "
            "create one with `python -m metrics.harness generate`"
        )

    gen_config = doc.get("config") or {}
    situation = gen_config.get("situation")
    g = gen_config.get("G")
    if not situation:
        sys.exit("error: plans file has no situation in its config")

    profile_ids = list(doc.get("profile_ids") or [])
    plans = doc.get("plans") or {}
    failures = doc.get("failures") or {}
    if args.profile:
        if args.profile not in profile_ids:
            sys.exit(f"error: profile {args.profile} is not in {args.plans}")
        profile_ids = [args.profile]
        plans = {pid: v for pid, v in plans.items() if pid == args.profile}
        failures = {pid: v for pid, v in failures.items() if pid == args.profile}
    if not plans:
        sys.exit("error: no plans to score in this file")

    if "consistency" in args.metrics and (g or 0) < 2:
        warnings.warn(
            f"G={g}: consistency requires G>=2; "
            "consistency scores will be null for all profiles.",
            stacklevel=1,
        )

    _eval_dir_on_path()
    from metrics.relevance import DEFAULT_RELEVANCE_REGION

    judge_model_id = args.judge_model or os.environ.get("EVAL_ANTHROPIC_MODEL")
    if not judge_model_id:
        sys.exit("error: EVAL_ANTHROPIC_MODEL is not set (required for LLM judging)")
    judge_region = args.judge_region or DEFAULT_RELEVANCE_REGION

    out_path = _output_path(args.results_out)
    config = {
        **gen_config,
        "plans_file": str(plans_path),
        "plans_generated_at": doc.get("generated_at"),
        "N": args.N,
        "metrics": sorted(args.metrics),
        "judge_model": judge_model_id,
        "judge_region": judge_region,
    }

    from metrics.bedrock_judge import BedrockJudge

    judge = BedrockJudge(model_id=judge_model_id, region=judge_region)
    judge.load_model()  # fail fast if credentials are missing

    relevance_client = None
    relevance_template = None
    if "relevance" in args.metrics:
        from metrics.relevance import load_relevance_prompt, make_bedrock_client

        relevance_client = make_bedrock_client(judge_region)
        relevance_template = load_relevance_prompt()

    consistency_scores: dict[str, list] = {}
    relevance_scores: dict[str, list] = {}

    to_score = [pid for pid in profile_ids if pid in plans]
    for i, pid in enumerate(to_score, 1):
        gens = plans[pid]
        print(f"[{i}/{len(to_score)}] {pid}", file=sys.stderr)
        if args.verbose:
            print(f"  {pid}: {len(gens)} plans", file=sys.stderr)

        if "consistency" in args.metrics:
            from metrics.consistency import score_consistency

            consistency_scores[pid] = [
                score_consistency(gens, judge, situation) for _ in range(args.N)
            ]

        if "relevance" in args.metrics:
            from metrics.relevance import score_relevance

            relevance_scores[pid] = [
                [
                    score_relevance(
                        gen,
                        relevance_client,
                        judge_model_id,
                        relevance_template,
                        situation,
                    )["tasks"]
                    for gen in gens
                ]
                for _ in range(args.N)
            ]

    from metrics.aggregate import compute_results

    results = compute_results(
        [{"id": pid} for pid in profile_ids],
        plans,
        consistency_scores,
        relevance_scores,
        config,
        failures,
    )
    out_path.write_text(json.dumps(results, indent=2))
    print(f"wrote results to {args.results_out}", file=sys.stderr)

    short = _short_profiles(plans, g)
    if failures or short:
        print(
            f"warning: the plans file is incomplete ({len(failures)} profile(s) with "
            f"no plans, {len(short)} with fewer than G={g}); see the coverage block",
            file=sys.stderr,
        )
    return 0


def _parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(
        prog="python -m metrics.harness",
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    sub = ap.add_subparsers(dest="command", required=True, metavar="{generate,score}")

    gen = sub.add_parser(
        "generate",
        help="call the hosted agent and save plans to a plans file",
        description="Generate G plans per profile from the hosted planner agent.",
    )
    gen.add_argument("profiles", help="Path to profiles JSON file")
    gen.add_argument("--profile", metavar="ID", help="Generate for a single profile ID only")
    gen.add_argument(
        "-G",
        type=int,
        default=3,
        metavar="N_GENS",
        help="Plan generations per profile (default: 3)",
    )
    gen.add_argument(
        "--agent-runtime-arn",
        default=os.environ.get("AGENT_RUNTIME_ARN"),
        help="ARN of the hosted planner runtime (default: $AGENT_RUNTIME_ARN)",
    )
    gen.add_argument(
        "--max-attempts",
        type=int,
        default=3,
        help="Tries per plan generation, including the first (default: 3)",
    )
    gen.add_argument(
        "-o",
        "--plans-out",
        default="plans.json",
        help="Where to write the plans file (default: plans.json)",
    )
    gen.add_argument("--verbose", action="store_true", help="Print per-profile plan counts")
    gen.set_defaults(func=_cmd_generate)

    score = sub.add_parser(
        "score",
        help="judge a saved plans file and write results.json",
        description="Score a plans file written by `generate`.",
    )
    score.add_argument("plans", help="Path to a plans file written by `generate`")
    score.add_argument("--profile", metavar="ID", help="Score a single profile ID only")
    score.add_argument(
        "-N",
        type=int,
        default=1,
        metavar="N_REPEATS",
        help="Judge repeats per profile (default: 1)",
    )
    score.add_argument(
        "--metrics",
        nargs="+",
        choices=sorted(_VALID_METRICS),
        default=sorted(_VALID_METRICS),
        help="Metrics to compute (default: all)",
    )
    score.add_argument(
        "--judge-model",
        default=None,
        help="Bedrock model ID for judging (overrides EVAL_ANTHROPIC_MODEL; required if not set)",
    )
    score.add_argument(
        "--judge-region",
        default=None,
        help="AWS region for judge model (default: eu-west-1)",
    )
    score.add_argument(
        "--results-out",
        default="results.json",
        help="Path for the results JSON output (default: results.json)",
    )
    score.add_argument("--verbose", action="store_true", help="Print per-profile plan counts")
    score.set_defaults(func=_cmd_score)
    return ap


def main(argv=None):
    """Entry point for the metrics harness."""
    args = _parser().parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
