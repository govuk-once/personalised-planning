r"""Standalone metrics harness: consistency and relevance.

Runs independently of the main pipeline — no truth file, no spine, no F1.
Plans come from the hosted planner agent in AgentCore Runtime. Set
AGENT_RUNTIME_ARN (or pass --agent-runtime-arn) and EVAL_ANTHROPIC_MODEL, and run
with AWS credentials that can invoke the runtime and call Bedrock.

Examples::

    # Both metrics, 3 plans per profile, 1 judge repeat
    python -m metrics.harness profiles.json -G 3 -N 1

    # Single profile, verbose
    python -m metrics.harness profiles.json --profile P013 -G 2 -N 2 --verbose

    # Consistency only, against an explicit runtime
    python -m metrics.harness profiles.json --metrics consistency -G 3 \\
        --agent-runtime-arn arn:aws:bedrock-agentcore:eu-west-2:123456789012:runtime/planner-abc

Knobs:
    G   = plan generations per profile (each is one call to the hosted agent).
    N   = judge repeats per metric per profile (smooths judge variance).

Relevance per profile = mean over plans of (mean over N repeats). Consistency
service stability is computed from the plans; holistic is the mean over N repeats.
Overall aggregate = mean of per-profile scores.

A failed plan generation is retried up to --max-attempts times if the error looks
transient (throttling, timeouts, 5xx, an empty reply); permanent errors such as
AccessDenied are not retried. Results are always written. The exit code is 1 if
any profile got no plans or fewer than G, and results.json has a "coverage" block.
"""

import argparse
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


def _build_config(
    args: argparse.Namespace, situation: str, judge_model_id: str, judge_region: str
) -> dict:
    return {
        "G": args.G,
        "N": args.N,
        "metrics": sorted(args.metrics),
        "judge_model": judge_model_id,
        "judge_region": judge_region,
        "agent_runtime_arn": args.agent_runtime_arn,
        "max_attempts": args.max_attempts,
        "situation": situation,
    }


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


def main(argv=None):
    """Entry point for the metrics harness."""
    ap = argparse.ArgumentParser(
        prog="python -m metrics.harness",
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    ap.add_argument("profiles", help="Path to profiles JSON file")
    ap.add_argument("--profile", metavar="ID", help="Run a single profile ID only")
    ap.add_argument(
        "-G",
        type=int,
        default=3,
        metavar="N_GENS",
        help="Plan generations per profile (default: 3)",
    )
    ap.add_argument(
        "-N",
        type=int,
        default=1,
        metavar="N_REPEATS",
        help="Judge repeats per profile (default: 1)",
    )
    ap.add_argument(
        "--metrics",
        nargs="+",
        choices=sorted(_VALID_METRICS),
        default=sorted(_VALID_METRICS),
        help="Metrics to compute (default: all)",
    )
    ap.add_argument(
        "--judge-model",
        default=None,
        help="Bedrock model ID for judging (overrides EVAL_ANTHROPIC_MODEL; required if not set)",
    )
    ap.add_argument(
        "--judge-region",
        default=None,
        help="AWS region for judge model (default: eu-west-1)",
    )
    ap.add_argument(
        "--agent-runtime-arn",
        default=os.environ.get("AGENT_RUNTIME_ARN"),
        help="ARN of the hosted planner runtime (default: $AGENT_RUNTIME_ARN)",
    )
    ap.add_argument(
        "--max-attempts",
        type=int,
        default=3,
        help="Tries per plan generation, including the first (default: 3)",
    )
    ap.add_argument(
        "--results-out",
        default="results.json",
        help="Path for the results JSON output (default: results.json)",
    )
    ap.add_argument(
        "--raw", metavar="PATH", help="Also write raw generations to this path"
    )
    ap.add_argument(
        "--verbose", action="store_true", help="Print per-profile plan counts"
    )
    args = ap.parse_args(argv)

    if args.max_attempts < 1:
        ap.error("--max-attempts must be at least 1")
    if args.G < 2 and "consistency" in args.metrics:
        warnings.warn(
            f"G={args.G}: consistency requires G>=2; "
            "consistency scores will be null for all profiles.",
            stacklevel=1,
        )

    # --- Load profiles ---
    profiles_data = _load(args.profiles)
    all_profiles = profiles_data.get("profiles") or profiles_data
    if args.profile:
        all_profiles = [p for p in all_profiles if p.get("id") == args.profile]
    if not all_profiles:
        sys.exit("error: no matching profiles found")

    # run_app is a sibling module; ensure it's importable
    _eval_dir = str(pathlib.Path(__file__).resolve().parents[1])
    if _eval_dir not in sys.path:
        sys.path.insert(0, _eval_dir)

    from metrics.relevance import DEFAULT_RELEVANCE_REGION
    from run_app import SITUATION, make_agent_client, profile_context

    if not args.agent_runtime_arn:
        sys.exit("error: AGENT_RUNTIME_ARN is not set (or pass --agent-runtime-arn)")
    try:
        agent_client = make_agent_client(args.agent_runtime_arn)
    except ValueError as exc:
        sys.exit(f"error: {exc}")

    judge_model_id = args.judge_model or os.environ.get("EVAL_ANTHROPIC_MODEL")
    if not judge_model_id:
        sys.exit("error: EVAL_ANTHROPIC_MODEL is not set (required for LLM judging)")
    judge_region = args.judge_region or DEFAULT_RELEVANCE_REGION

    config = _build_config(args, SITUATION, judge_model_id, judge_region)

    from metrics.bedrock_judge import BedrockJudge

    judge = BedrockJudge(model_id=judge_model_id, region=judge_region)
    judge.load_model()  # fail fast if credentials are missing

    relevance_client = None
    relevance_template = None
    if "relevance" in args.metrics:
        from metrics.relevance import load_relevance_prompt, make_bedrock_client

        relevance_client = make_bedrock_client(judge_region)
        relevance_template = load_relevance_prompt()

    # --- Main loop ---
    generations_by_profile: dict[str, list[dict]] = {}
    failures: dict[str, str] = {}
    consistency_scores: dict[str, list] = {}
    relevance_scores: dict[str, list] = {}

    total = len(all_profiles)
    for i, profile in enumerate(all_profiles, 1):
        pid = profile.get("id", f"profile_{i}")
        print(f"[{i}/{total}] {pid}", file=sys.stderr)

        # --- Generate G plans ---
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

        if not gens:
            failures[pid] = last_error or "no plans generated"
            print(f"  {pid}: all generations failed, skipping", file=sys.stderr)
            continue

        generations_by_profile[pid] = gens
        if args.verbose:
            print(f"  {pid}: {len(gens)}/{args.G} plans", file=sys.stderr)

        # --- Score N times ---
        if "consistency" in args.metrics:
            from metrics.consistency import score_consistency

            pid_cons = []
            for _ in range(args.N):
                pid_cons.append(score_consistency(gens, judge, SITUATION))
            consistency_scores[pid] = pid_cons

        if "relevance" in args.metrics:
            from metrics.relevance import score_relevance

            pid_rel = []
            for _ in range(args.N):
                repeat = [
                    score_relevance(
                        gen,
                        relevance_client,
                        judge_model_id,
                        relevance_template,
                        SITUATION,
                    )["tasks"]
                    for gen in gens
                ]
                pid_rel.append(repeat)
            relevance_scores[pid] = pid_rel

    # --- Aggregate and write ---
    from metrics.aggregate import compute_results

    results = compute_results(
        all_profiles,
        generations_by_profile,
        consistency_scores,
        relevance_scores,
        config,
        failures,
    )

    out_path = pathlib.Path(args.results_out).resolve()
    if not out_path.parent.is_dir():
        sys.exit(f"error: output directory does not exist: {out_path.parent}")
    out_path.write_text(json.dumps(results, indent=2))
    print(f"wrote results to {args.results_out}", file=sys.stderr)

    if args.raw:
        raw_path = pathlib.Path(args.raw).resolve()
        raw_path.write_text(json.dumps(generations_by_profile, indent=2))
        print(f"wrote raw generations to {args.raw}", file=sys.stderr)

    short = [pid for pid, gens in generations_by_profile.items() if len(gens) < args.G]
    print(f"scored {len(generations_by_profile)}/{total} profiles", file=sys.stderr)
    for pid, error in failures.items():
        print(f"  skipped {pid}: {error}", file=sys.stderr)
    for pid in short:
        n = len(generations_by_profile[pid])
        print(f"  short {pid}: {n}/{args.G} plans", file=sys.stderr)

    return 1 if failures or short else 0


if __name__ == "__main__":
    sys.exit(main())
