r"""Standalone metrics harness: faithfulness, consistency, relevance.

Runs independently of the main pipeline — no truth file, no spine, no F1.

Examples::

    # All metrics, 3 plans per profile, 1 judge repeat
    python -m metrics.harness profiles.json -G 3 -N 1

    # Single profile, verbose
    python -m metrics.harness profiles.json --profile P013 -G 2 -N 2 --verbose

    # Consistency only, using a remote MCP gateway
    python -m metrics.harness profiles.json --metrics consistency -G 3 \\
        --mcp-mode remote --graph-gateway-url https://...

Knobs:
    G   = plan generations per profile (each is one full agent run).
    N   = judge repeats per metric per profile (smooths judge variance).

Per-profile score = mean over G x N (faithfulness/relevance) or N (consistency).
Overall aggregate = mean of per-profile scores.
"""

import argparse
import json
import os
import pathlib
import sys
import warnings


_VALID_METRICS = frozenset({"faithfulness", "consistency", "relevance"})


def _load(path: str):
    """Load and parse a JSON file, exiting with an error message on failure."""
    p = pathlib.Path(path).resolve()
    if not p.is_file():
        sys.exit(f"error: not a file: {path}")
    return json.loads(p.read_text())


def _build_config(
    args: argparse.Namespace, situation: str, judge_model_id: str
) -> dict:
    return {
        "G": args.G,
        "N": args.N,
        "metrics": sorted(args.metrics),
        "judge_model": judge_model_id,
        "judge_region": args.judge_region,
        "agent_model": os.environ.get("ANTHROPIC_MODEL"),
        "agent_region": args.agent_region or os.environ.get("AWS_REGION"),
        "mcp_mode": args.mcp_mode or os.environ.get("MCP_MODE"),
        "mode": args.mode,
        "situation": situation,
    }


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
        "--agent-model",
        default=None,
        help="Bedrock model ID for plan generation (overrides ANTHROPIC_MODEL)",
    )
    ap.add_argument(
        "--agent-region",
        default=None,
        help="Override AWS_REGION env var for the planner agent",
    )
    ap.add_argument(
        "--mcp-mode",
        choices=["local", "remote"],
        default=None,
        help="Override MCP_MODE env var",
    )
    ap.add_argument(
        "--graph-server-path",
        default=None,
        help="Override GRAPH_SERVER_PATH (local MCP mode)",
    )
    ap.add_argument(
        "--graph-gateway-url",
        default=None,
        help="Override GRAPH_GATEWAY_URL (remote MCP mode)",
    )
    ap.add_argument(
        "--mode",
        choices=["in-process", "endpoint"],
        default="in-process",
        help="How to invoke the planner (default: in-process)",
    )
    ap.add_argument(
        "--endpoint",
        default="http://localhost:8000/plan",
        help="Plan API endpoint for --mode endpoint",
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
        "--verbose", action="store_true", help="Print per-generation log output"
    )
    args = ap.parse_args(argv)

    # --- Validate mutually exclusive constraints ---
    if "faithfulness" in args.metrics and args.mode == "endpoint":
        sys.exit(
            "error: --mode endpoint cannot capture retrieval context; "
            "faithfulness requires --mode in-process"
        )
    if args.G < 2 and "consistency" in args.metrics:
        warnings.warn(
            f"G={args.G}: consistency requires G>=2; "
            "consistency scores will be null for all profiles.",
            stacklevel=1,
        )

    # --- Apply env var overrides before any agent imports ---
    if args.agent_model:
        os.environ["ANTHROPIC_MODEL"] = args.agent_model
    if args.mode == "in-process" and not os.environ.get("ANTHROPIC_MODEL"):
        sys.exit(
            "error: ANTHROPIC_MODEL is not set (required for in-process plan generation)"
        )
    if args.agent_region:
        os.environ["AWS_REGION"] = args.agent_region
    if args.mcp_mode:
        os.environ["MCP_MODE"] = args.mcp_mode
    if args.graph_server_path:
        os.environ["GRAPH_SERVER_PATH"] = args.graph_server_path
    if args.graph_gateway_url:
        os.environ["GRAPH_GATEWAY_URL"] = args.graph_gateway_url

    # --- Load profiles ---
    profiles_data = _load(args.profiles)
    all_profiles = profiles_data.get("profiles") or profiles_data
    if args.profile:
        all_profiles = [p for p in all_profiles if p.get("id") == args.profile]
    if not all_profiles:
        sys.exit("error: no matching profiles found")

    # --- Lazy imports (agent import changes cwd; do after env overrides) ---
    # run_app is a sibling module; ensure it's importable
    _eval_dir = str(pathlib.Path(__file__).resolve().parents[1])
    if _eval_dir not in sys.path:
        sys.path.insert(0, _eval_dir)

    from metrics.relevance import DEFAULT_RELEVANCE_REGION
    from run_app import SITUATION

    judge_model_id = args.judge_model or os.environ.get("EVAL_ANTHROPIC_MODEL")
    if not judge_model_id:
        sys.exit("error: EVAL_ANTHROPIC_MODEL is not set (required for LLM judging)")
    judge_region = args.judge_region or DEFAULT_RELEVANCE_REGION

    # Build config now that we have SITUATION and resolved model IDs
    config = _build_config(args, SITUATION, judge_model_id)

    from metrics.bedrock_judge import BedrockJudge

    judge = BedrockJudge(model_id=judge_model_id, region=judge_region)
    judge.load_model()  # fail fast if credentials are missing

    relevance_client = None
    relevance_template = None
    if "relevance" in args.metrics:
        from metrics.relevance import load_relevance_prompt, make_bedrock_client

        relevance_client = make_bedrock_client(judge_region)
        relevance_template = load_relevance_prompt()

    generate_fn = None
    StructuredLogger = None
    if args.mode == "in-process":
        from metrics.generation import generate_plans as generate_fn, StructuredLogger  # type: ignore[assignment]

    # --- Main loop ---
    generations_by_profile: dict[str, list[dict]] = {}
    faithfulness_scores: dict[str, list] = {}
    consistency_scores: dict[str, list] = {}
    relevance_scores: dict[str, list] = {}

    total = len(all_profiles)
    for i, profile in enumerate(all_profiles, 1):
        pid = profile.get("id", f"profile_{i}")
        print(f"[{i}/{total}] {pid}", file=sys.stderr)

        # --- Generate G plans ---
        if args.mode == "in-process":
            log = StructuredLogger(
                session_id=f"eval-{pid}",
                user_id="eval-harness",
                agent_name="planner",
            )
            gens = generate_fn(profile, args.G, log)
        else:
            from run_app import call_api, profile_context

            ctx = profile_context(profile)
            gens = []
            for g in range(args.G):
                try:
                    resp = call_api(args.endpoint, ctx)
                    plan = resp.get("plan")
                    if plan:
                        gens.append(
                            {"plan": plan, "retrieval_context": [], "context": ctx}
                        )
                    else:
                        print(f"  gen {g + 1}: no plan in response", file=sys.stderr)
                except RuntimeError as exc:
                    print(f"  gen {g + 1} failed: {exc}", file=sys.stderr)

        if not gens:
            print(f"  {pid}: all generations failed, skipping", file=sys.stderr)
            continue

        generations_by_profile[pid] = gens
        if args.verbose:
            print(f"  {pid}: {len(gens)}/{args.G} plans", file=sys.stderr)

        # --- Score N times ---
        if "faithfulness" in args.metrics:
            from metrics.faithfulness import score_faithfulness

            pid_faith = []
            for _ in range(args.N):
                pid_faith.append(
                    [score_faithfulness(gen, judge, SITUATION) for gen in gens]
                )
            faithfulness_scores[pid] = pid_faith

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
        faithfulness_scores,
        consistency_scores,
        relevance_scores,
        config,
    )

    out_path = pathlib.Path(args.results_out).resolve()
    if not out_path.parent.is_dir():
        sys.exit(f"error: output directory does not exist: {out_path.parent}")
    out_path.write_text(json.dumps(results, indent=2))
    print(f"wrote results to {args.results_out}", file=sys.stderr)

    if args.raw:
        raw_path = pathlib.Path(args.raw).resolve()
        raw_data = {
            pid: [
                {
                    "plan": g["plan"],
                    "retrieval_context": g.get("retrieval_context", []),
                }
                for g in gens
            ]
            for pid, gens in generations_by_profile.items()
        }
        raw_path.write_text(json.dumps(raw_data, indent=2))
        print(f"wrote raw generations to {args.raw}", file=sys.stderr)

    return 0


if __name__ == "__main__":
    sys.exit(main())
