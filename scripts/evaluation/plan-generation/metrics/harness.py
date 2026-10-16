r"""Standalone metrics harness: consistency and relevance, in two steps.

    python -m metrics.harness generate profiles.json -G 3 -o plans.json
    python -m metrics.harness score plans.json -N 2 --results-out results.json

``generate`` calls the hosted planner agent G times per profile and saves the
plans, so the slow part runs once. ``score`` judges a plans file N times per
metric and can be rerun as often as you like. Run both from
scripts/evaluation/plan-generation/ (the parent of this package); see README
Part 4 for the flags, retries, and the plans file and coverage formats.
"""

import argparse
import datetime
import json
import os
import pathlib
import sys
import warnings

_VALID_METRICS = frozenset({"consistency", "relevance"})

_PLANS_KIND = "plan-generations"
_PLANS_VERSION = 1


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


def _short_profiles(plans: dict[str, list], g: int) -> list[str]:
    """Profiles that got at least one plan but fewer than G."""
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

    from metrics.agent_calls import generate_one
    from run_app import make_agent_client, profile_context, profile_situation

    # Check every situation before the first slow agent call.
    try:
        situations = [profile_situation(p) for p in all_profiles]
    except ValueError as exc:
        sys.exit(f"error: {exc}")

    if not args.agent_runtime_arn:
        sys.exit("error: AGENT_RUNTIME_ARN is not set (or pass --agent-runtime-arn)")
    try:
        client = make_agent_client(args.agent_runtime_arn)
    except ValueError as exc:
        sys.exit(f"error: {exc}")

    out_path = _output_path(args.plans_out)
    profile_ids = [p.get("id", f"profile_{i}") for i, p in enumerate(all_profiles, 1)]
    plans: dict[str, list[dict]] = {}
    failures: dict[str, str] = {}
    doc = {
        "kind": _PLANS_KIND,
        "version": _PLANS_VERSION,
        "generated_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "config": {
            "G": args.G,
            "agent_runtime_arn": args.agent_runtime_arn,
            "max_attempts": args.max_attempts,
            "profiles_file": str(pathlib.Path(args.profiles).resolve()),
            "profile": args.profile,
        },
        "profile_ids": profile_ids,
        "plans": plans,
        "failures": failures,
    }

    total = len(all_profiles)
    for i, (pid, profile, situation) in enumerate(
        zip(profile_ids, all_profiles, situations, strict=True), 1
    ):
        print(f"[{i}/{total}] {pid}", file=sys.stderr)
        ctx = profile_context(profile)
        gens = []
        last_error = None
        for g in range(args.G):
            gen, error = generate_one(
                client, args.agent_runtime_arn, situation, ctx, args.max_attempts
            )
            if gen:
                gens.append(gen)
            else:
                last_error = error
                print(f"  gen {g + 1} failed: {error}", file=sys.stderr)

        if gens:
            plans[pid] = gens
        else:
            failures[pid] = last_error
            print(f"  {pid}: all generations failed, skipping", file=sys.stderr)

        # Save after every profile so an interrupted run keeps the work done so far.
        _write_json_atomic(out_path, doc)

    print(f"wrote plans to {args.plans_out}", file=sys.stderr)

    short = _short_profiles(plans, args.G)
    print(f"generated plans for {len(plans)}/{total} profiles", file=sys.stderr)
    for pid, error in failures.items():
        print(f"  skipped {pid}: {error}", file=sys.stderr)
    for pid in short:
        print(f"  short {pid}: {len(plans[pid])}/{args.G} plans", file=sys.stderr)

    return 1 if failures or short else 0


def _cmd_score(args: argparse.Namespace) -> int:
    """Judge a saved plans file N times per metric and write results.json."""
    if args.N < 1:
        sys.exit("error: -N must be at least 1")
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
    g = gen_config.get("G")
    if not isinstance(g, int) or g < 1:
        sys.exit("error: plans file has no valid G in its config")

    profile_ids = list(doc.get("profile_ids") or [])
    plans = doc.get("plans") or {}
    failures = doc.get("failures") or {}
    if args.profile:
        if args.profile not in profile_ids:
            sys.exit(f"error: profile {args.profile} is not in {args.plans}")
        profile_ids = [args.profile]
        plans = {k: v for k, v in plans.items() if k in profile_ids}
        failures = {k: v for k, v in failures.items() if k in profile_ids}
    if not plans:
        sys.exit("error: no plans to score in this file")

    # Each profile has one situation, saved with every generation.
    situations = {}
    for pid, gens in plans.items():
        found = {gen.get("situation") for gen in gens}
        if len(found) != 1 or not next(iter(found)):
            sys.exit(f"error: {pid} has a missing or inconsistent situation")
        situations[pid] = found.pop()

    if "consistency" in args.metrics and g < 2:
        warnings.warn(
            f"G={g}: consistency requires G>=2; "
            "consistency scores will be null for all profiles.",
            stacklevel=1,
        )

    from metrics.relevance import DEFAULT_RELEVANCE_REGION

    judge_model_id = args.judge_model or os.environ.get("EVAL_ANTHROPIC_MODEL")
    if not judge_model_id:
        sys.exit("error: EVAL_ANTHROPIC_MODEL is not set (required for LLM judging)")
    judge_region = args.judge_region or DEFAULT_RELEVANCE_REGION

    out_path = _output_path(args.results_out)
    config = {
        **{k: v for k, v in gen_config.items() if k != "agent_runtime_arn"},
        "plans_file": str(pathlib.Path(args.plans).resolve()),
        "plans_generated_at": doc.get("generated_at"),
        "scored_profile": args.profile,
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

    for i, (pid, gens) in enumerate(plans.items(), 1):
        print(f"[{i}/{len(plans)}] {pid}", file=sys.stderr)

        if "consistency" in args.metrics:
            from metrics.consistency import score_consistency

            consistency_scores[pid] = [
                score_consistency(gens, judge, situations[pid]) for _ in range(args.N)
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
                    )["tasks"]
                    for gen in gens
                ]
                for _ in range(args.N)
            ]

    from metrics.aggregate import compute_results

    results = compute_results(
        profile_ids,
        plans,
        consistency_scores,
        relevance_scores,
        config,
        failures,
    )
    text = json.dumps(results, indent=2)
    runtime_arn = gen_config.get("agent_runtime_arn")
    if runtime_arn:
        # The ARN carries the AWS account ID, and AWS error messages can quote it.
        text = text.replace(runtime_arn, "<runtime-arn>")
    out_path.write_text(text)
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
    gen.add_argument(
        "--profile", metavar="ID", help="Generate for a single profile ID only"
    )
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
    score.set_defaults(func=_cmd_score)
    return ap


def main(argv=None):
    """Entry point for the metrics harness."""
    args = _parser().parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
