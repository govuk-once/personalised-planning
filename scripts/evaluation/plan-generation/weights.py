r"""Weight the profiles so they represent real users, not just cover every journey.

    python weights.py data/profiles/driving_profiles_v5.json \
        data/weights/driving_weights_v1.json -o data/profiles/driving_profiles_v5_w1.json

The generated profiles cover every journey through the questionnaire once, so
common and rare users count the same. The weights file (`targets`) says what
share of people give each answer, among those asked that question. Each
profile gets a `weight` (all weights sum to 1) by raking: for each targeted
question in turn, the weights of the profiles asked it are rescaled until each
answer's share of their total weight matches the target, and this repeats
until nothing moves. Questions without a target keep the spread they have.

With `--sample N`, N profiles are drawn at random in proportion to their weight
(seeded), and only the distinct ones are written, each with weight draws / N.
Use it to run a smaller, representative set.

The output is the profiles file plus `weight` on every profile, so it can be
passed to `metrics.harness generate` and `score --weights`. Targets for
answers no profile gives are dropped (with a warning) and the rest rescaled; a
target for a question no profile is asked, or a profile answer with no target,
is an error and nothing is written.
"""

import argparse
import json
import os
import pathlib
import random
import sys
from collections import Counter, defaultdict


def load(path):
    """Read a JSON file."""
    resolved = pathlib.Path(path).resolve()
    if not resolved.is_file():
        raise ValueError(f"Not a valid file path: {path}")
    return json.loads(resolved.read_text())


def load_targets(targets, profiles):
    """Check the targets against the profiles and normalise them.

    Args:
        targets: Question id mapped to answer id mapped to share. Keys starting
            with an underscore (such as `_source`) are notes and are dropped.
        profiles: Synthetic profile records.

    Returns:
        Question id mapped to answer id mapped to share, each question
        summing to 1 over the answers that profiles give.

    Raises:
        ValueError: If a question is never asked, a profile answer has no
            target, or a target is negative or all zero.
    """
    given = defaultdict(set)
    for p in profiles:
        for q, a in p["answers"].items():
            given[q].add(a)

    out = {}
    for q, table in targets.items():
        table = {a: v for a, v in table.items() if not a.startswith("_")}
        if q not in given:
            raise ValueError(f"{q}: no profile is asked this question")
        if missing := given[q] - table.keys():
            raise ValueError(f"{q}: no target for {', '.join(sorted(missing))}")
        if unused := table.keys() - given[q]:
            print(
                f"warning: {q}: no profile answers {', '.join(sorted(unused))}; "
                "dropped",
                file=sys.stderr,
            )
        kept = {a: table[a] for a in given[q]}
        total = sum(kept.values())
        if min(kept.values()) < 0 or total <= 0:
            raise ValueError(f"{q}: targets must be non-negative and not all zero")
        out[q] = {a: v / total for a, v in kept.items()}
    return out


def rake(profiles, targets, rounds=100, tol=1e-9):
    """Weight profiles so each targeted answer holds its target share.

    Args:
        profiles: Synthetic profile records.
        targets: Normalised targets from `load_targets`.
        rounds: Most passes over the targeted questions.
        tol: Stop when no weight is rescaled by more than this fraction.

    Returns:
        Profile id mapped to weight (summing to 1), and the rounds used.
    """
    w = {p["id"]: 1 / len(profiles) for p in profiles}
    used = 0
    for _ in range(rounds):
        used += 1
        worst = 0.0
        for q, table in targets.items():
            asked = [p for p in profiles if q in p["answers"]]
            total = sum(w[p["id"]] for p in asked)
            held = defaultdict(float)
            for p in asked:
                held[p["answers"][q]] += w[p["id"]]
            for p in asked:
                a = p["answers"][q]
                if held[a]:
                    factor = table[a] * total / held[a]
                    worst = max(worst, abs(factor - 1))
                    w[p["id"]] *= factor
        if worst < tol:
            break
    norm = sum(w.values())
    return {pid: v / norm for pid, v in w.items()}, used


def achieved(profiles, weights, q):
    """Share of the weight of profiles asked `q` held by each answer."""
    asked = [p for p in profiles if q in p["answers"]]
    total = sum(weights[p["id"]] for p in asked)
    held = Counter()
    for p in asked:
        held[p["answers"][q]] += weights[p["id"]] / total
    return held


def sample(profiles, weights, n, seed):
    """Draw n profiles in proportion to weight; keep each distinct one once.

    Args:
        profiles: Synthetic profile records.
        weights: Profile id mapped to weight.
        n: Number of draws.
        seed: Random seed.

    Returns:
        The distinct profiles drawn, in their original order, each with
        weight draws / n.
    """
    draws = Counter(
        p["id"]
        for p in random.Random(seed).choices(
            profiles, weights=[weights[p["id"]] for p in profiles], k=n
        )
    )
    return [{**p, "weight": draws[p["id"]] / n} for p in profiles if p["id"] in draws]


def report(profiles, targets, weights, rounds, ess):
    """Print how close each targeted answer got to its target."""
    print(
        f"raked {len(profiles)} profiles over {len(targets)} targeted questions "
        f"in {rounds} rounds",
        file=sys.stderr,
    )
    print(f"effective sample size: {ess:.1f} of {len(profiles)}", file=sys.stderr)
    print(f"{'question':<24}{'answer':<26}target  achieved  profiles", file=sys.stderr)
    for q, table in targets.items():
        got = achieved(profiles, weights, q)
        for a, share in sorted(table.items(), key=lambda kv: -kv[1]):
            count = sum(1 for p in profiles if p["answers"].get(q) == a)
            print(
                f"{q:<24}{a:<26}{share:>6.3f}  {got[a]:>8.3f}  {count:>8}",
                file=sys.stderr,
            )
    ranked = sorted(weights, key=weights.get, reverse=True)
    print(
        f"heaviest: {ranked[0]} ({weights[ranked[0]]:.4f})   "
        f"lightest: {ranked[-1]} ({weights[ranked[-1]]:.4f})",
        file=sys.stderr,
    )


def main(argv=None):
    """Entry point."""
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    ap.add_argument("profiles", help="profiles file")
    ap.add_argument("weights", help="weights file with `targets`")
    ap.add_argument("-o", "--out", required=True, help="where to write the profiles")
    ap.add_argument(
        "--sample",
        type=int,
        metavar="N",
        help="draw N profiles by weight, keep the distinct",
    )
    ap.add_argument(
        "--seed", type=int, default=0, help="seed for --sample (default: 0)"
    )
    args = ap.parse_args(argv)

    data, spec = load(args.profiles), load(args.weights)
    profiles = data["profiles"]
    out = pathlib.Path(args.out).resolve()
    if not out.parent.is_dir():
        print(f"error: output directory does not exist: {out.parent}", file=sys.stderr)
        return 1

    try:
        targets = load_targets(spec["targets"], profiles)
    except ValueError as e:
        print(f"error: {e}", file=sys.stderr)
        return 1

    weights, rounds = rake(profiles, targets)
    ess = 1 / sum(v * v for v in weights.values())
    report(profiles, targets, weights, rounds, ess)

    if args.sample:
        written = sample(profiles, weights, args.sample, args.seed)
        print(
            f"sampled {args.sample} draws -> {len(written)} distinct profiles",
            file=sys.stderr,
        )
    else:
        written = [{**p, "weight": weights[p["id"]]} for p in profiles]

    meta = {
        **data.get("meta", {}),
        "count": len(written),
        "weights": {
            "file": args.weights,
            "method": "raking",
            "effective_sample_size": round(ess, 1),
            "sample": {"n": args.sample, "seed": args.seed} if args.sample else None,
        },
    }
    tmp = out.with_name(out.name + ".tmp")
    tmp.write_text(json.dumps({**data, "meta": meta, "profiles": written}, indent=2))
    os.replace(tmp, out)
    print(f"wrote {out}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
