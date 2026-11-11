"""Score a plans file's sessions with Amazon Bedrock AgentCore Evaluations.

python -m metrics.agentcore setup
python -m metrics.agentcore evaluate data/plans.json
"""

import argparse
import json
import os
import pathlib
import sys
import time

import boto3

HERE = pathlib.Path(__file__).parent
REGION = "eu-west-2"
BUILT_IN = ["Builtin.Faithfulness", "Builtin.ToolSelectionAccuracy"]
DONE = {"COMPLETED", "COMPLETED_WITH_ERRORS", "FAILED", "STOPPED"}

RUNS = (
    "It was run several times for the same person, in one session. Each turn "
    "is one run and ends in a plan, numbered in order.\n\n"
    "<session>\n{context}\n</session>"
)

# Each judge: its level, this harness's prompt, what AgentCore shows it, its score.
JUDGES = {
    "pp_plan_relevance": (
        "TRACE",
        "relevance_prompt.md",
        "The last user message holds the person's situation and the facts known "
        "about them. Judge every task of the plan.\n\n"
        "<conversation>\n{context}\n</conversation>\n\n"
        "<plan>\n{assistant_turn}\n</plan>",
        "the plan's tasks that are relevant",
    ),
    "pp_plan_structure_consistency": (
        "SESSION",
        "structure_consistency_prompt.md",
        f"{RUNS}\n\nCompare the structure of each pair of plans.",
        "pairs of plans with no difference",
    ),
    "pp_plan_fact_consistency": (
        "SESSION",
        "fact_consistency_prompt.md",
        f"{RUNS}\n\nFor each government service in two or more plans, compare "
        "what those plans say about it. If there is none, score 1.0.",
        "those services with no contradiction",
    ),
}


def instructions(prompt: str, shown: str, share: str) -> str:
    """A judge's instructions: this harness's rules, on what AgentCore shows."""
    text = (HERE / prompt).read_text()
    rules = text[text.index("How to read these:") : text.index("## Output")]
    rules = rules.replace("<tasks>\n{tasks}\n</tasks>\n\n", "")
    rules = rules.replace("{{", "").replace("}}", "")
    return (
        f"You are evaluating a GOV.UK planning service. {shown}\n\n"
        "Ignore the tool calls: they are the service's own research.\n\n"
        f"{rules}## Score\n\nThe share of {share}, to the nearest tenth. "
        "In your reasoning, list what you counted against it."
    )


def config(prompt: str, shown: str, share: str, model: str) -> dict:
    """An evaluator that scores from 0 to 1, in tenths."""
    tenths = [
        {"value": n / 10, "label": f"{n * 10}%", "definition": f"About {n * 10}%"}
        for n in range(10, -1, -1)
    ]
    return {
        "llmAsAJudge": {
            "instructions": instructions(prompt, shown, share),
            "ratingScale": {"numerical": tenths},
            "modelConfig": {
                "bedrockEvaluatorModelConfig": {
                    "modelId": model,
                    "inferenceConfig": {"maxTokens": 4096},
                }
            },
        }
    }


def evaluator_ids(control) -> dict[str, str]:
    """This account's evaluators, name to id."""
    found = control.list_evaluators(maxResults=100)["evaluators"]
    return {evaluator["evaluatorName"]: evaluator["evaluatorId"] for evaluator in found}


def setup(model: str) -> None:
    """Create or update the judges."""
    control = boto3.client("bedrock-agentcore-control", region_name=REGION)
    existing = evaluator_ids(control)
    for name, (level, *rest) in JUDGES.items():
        judge = config(*rest, model)
        if name in existing:
            control.update_evaluator(evaluatorId=existing[name], evaluatorConfig=judge)
        else:
            control.create_evaluator(
                evaluatorName=name, level=level, evaluatorConfig=judge
            )
        print(f"{name}: ready")


def evaluate(plans: str) -> int:
    """Score the sessions of a plans file, and print each judge's average."""
    doc = json.loads(pathlib.Path(plans).read_text())
    generations = [gen for gens in doc["plans"].values() for gen in gens]
    sessions = sorted({gen["session_id"] for gen in generations})
    runtime = doc["config"]["agent_runtime_arn"].split("/")[-1]
    control = boto3.client("bedrock-agentcore-control", region_name=REGION)
    agentcore = boto3.client("bedrock-agentcore", region_name=REGION)
    service = control.get_agent_runtime(agentRuntimeId=runtime)["agentRuntimeName"]

    ids = evaluator_ids(control)
    # Comparing a person's plans needs more than one each.
    several = len(generations) > len(sessions)
    judges = [name for name in JUDGES if several or JUDGES[name][0] == "TRACE"]
    evaluators = [ids[name] for name in judges] + BUILT_IN
    job = agentcore.start_batch_evaluation(
        batchEvaluationName=f"pp_plans_{int(time.time())}",
        evaluators=[{"evaluatorId": evaluator} for evaluator in evaluators],
        dataSourceConfig={
            "cloudWatchLogs": {
                "serviceNames": [f"{service}.DEFAULT"],
                "logGroupNames": [f"/aws/bedrock-agentcore/runtimes/{runtime}-DEFAULT"],
                "filterConfig": {"sessionIds": sessions},
            }
        },
    )
    while job["status"] not in DONE:
        print(f"{job['status']}: {len(sessions)} sessions", file=sys.stderr)
        time.sleep(30)
        job = agentcore.get_batch_evaluation(batchEvaluationId=job["batchEvaluationId"])

    names = {evaluator: name for name, evaluator in ids.items()}
    print(job["status"])
    for summary in job.get("evaluationResults", {}).get("evaluatorSummaries", []):
        name = names.get(summary["evaluatorId"], summary["evaluatorId"])
        average = summary.get("statistics", {}).get("averageScore")
        print(f"  {name:<32} {average}  ({summary.get('totalEvaluated', 0)} scored)")
    return 0 if job["status"] == "COMPLETED" else 1


def main() -> int:
    """Run a command."""
    parser = argparse.ArgumentParser(prog="python -m metrics.agentcore")
    parser.add_argument("command", choices=["setup", "evaluate"])
    parser.add_argument("plans", nargs="?", help="from metrics.harness generate")
    parser.add_argument("--judge-model", default=os.environ.get("EVAL_ANTHROPIC_MODEL"))
    args = parser.parse_args()
    if args.command == "evaluate":
        return evaluate(args.plans)
    if not args.judge_model:
        sys.exit("error: EVAL_ANTHROPIC_MODEL is not set (or pass --judge-model)")
    setup(args.judge_model)
    return 0


if __name__ == "__main__":
    sys.exit(main())
