"""Build a single-file HTML dashboard over evaluation results files.

Reads two kinds of results file in a directory:

- `metrics.harness score` results: relevance and consistency;
- `run_app.py --results-out` results: plan quality against the answer key
  (precision, recall, F1, and which steps each plan covered).

Files that scored the same plans (the same `plans_file` and
`plans_generated_at` in their `config`) are paired into one evaluation, so the
page can show both kinds of result side by side for each profile. A file with
no partner still shows on its own. Each scored profile's situation, readable
answers and weight are added from the profiles file the run recorded, and the
lot is embedded in one HTML page with a dropdown to switch between
evaluations. The page needs no server or network: open it straight from disk.
Re-run this script after a new `score` run to pick it up.

Files in other formats (`truth.py score` output, review packets) are skipped
with a note.

Usage:
    python dashboard.py
    python dashboard.py data/results -o data/results/dashboard.html
"""

from __future__ import annotations

import argparse
import json
import pathlib
import sys

HERE = pathlib.Path(__file__).resolve().parent
TEMPLATE = HERE / "dashboard_template.html"
METRIC_KEYS = ("consistency", "relevance")


def _is_harness_result(doc) -> bool:
    """Whether `doc` looks like a results file from `metrics.harness score`."""
    return (
        isinstance(doc, dict) and "config" in doc and any(k in doc for k in METRIC_KEYS)
    )


def _is_quality_result(doc) -> bool:
    """Whether `doc` looks like a plan-quality results file from `run_app.py`.

    Only files that record what they scored (a `config`, written since
    `--from-plans` was added) can be paired, so older files are skipped.
    """
    return (
        isinstance(doc, dict)
        and isinstance(doc.get("config"), dict)
        and isinstance(doc.get("scoring"), dict)
        and "per_profile" in doc["scoring"]
    )


def _pair_key(doc) -> tuple[str, str] | None:
    """What identifies the plans a results file scored, if it records them.

    The file name rather than the full path, so results still pair after the
    repo has moved; the timestamp tells two plans files of the same name apart.
    """
    config = doc.get("config") or {}
    if not config.get("plans_file") or not config.get("plans_generated_at"):
        return None
    return pathlib.Path(config["plans_file"]).name, config["plans_generated_at"]


def _resolve(path: str | None, near: pathlib.Path) -> pathlib.Path | None:
    """Find a profiles file recorded in a run's config, even if the repo moved.

    The harness records the path it was given, which may not exist where the
    dashboard is built. Fall back to the same file name beside the results file,
    then under `data/profiles/`.
    """
    if not path:
        return None
    p = pathlib.Path(path)
    if p.is_file():
        return p
    for folder in (near, HERE / "data" / "profiles"):
        if (folder / p.name).is_file():
            return folder / p.name
    return None


def _scored_ids(harness: dict | None, quality: dict | None) -> set[str]:
    """Profile ids scored by either results file."""
    ids = {
        pid
        for key in METRIC_KEYS
        for pid in ((harness or {}).get(key) or {}).get("per_profile", {})
    }
    ids |= {
        row["profile_id"]
        for row in ((quality or {}).get("scoring") or {}).get("per_profile", [])
    }
    return ids


def _profile_context(
    harness: dict | None, quality: dict | None, near: pathlib.Path
) -> dict[str, dict]:
    """Situation, readable answers and weight for each profile either run scored."""
    path = None
    for doc in (harness, quality):
        config = (doc or {}).get("config", {})
        path = path or _resolve(config.get("weights_file"), near)
        path = path or _resolve(config.get("profiles_file"), near)
    if path is None:
        return {}
    data = json.loads(path.read_text())
    profiles = data["profiles"] if isinstance(data, dict) else data
    scored = _scored_ids(harness, quality)
    return {
        p["id"]: {
            "situation": p.get("situation"),
            "readable": p.get("readable", {}),
            "weight": p.get("weight"),
        }
        for p in profiles
        if p.get("id") in scored
    }


def _load_results(results_dir: pathlib.Path):
    """Harness and plan-quality results in `results_dir`, plus skipped files."""
    harness, quality, skipped = [], [], []
    for path in sorted(results_dir.glob("*.json")):
        try:
            doc = json.loads(path.read_text())
        except (OSError, json.JSONDecodeError) as e:
            skipped.append(f"{path.name} (unreadable: {e})")
            continue
        if _is_harness_result(doc):
            harness.append((path.name, doc))
        elif _is_quality_result(doc):
            quality.append((path.name, doc))
        else:
            skipped.append(f"{path.name} (not a harness or plan-quality results file)")
    return harness, quality, skipped


def _newest_first(items):
    """(name, doc) pairs, most recently scored first."""
    return sorted(items, key=lambda kv: kv[1].get("generated_at", ""), reverse=True)


def _evaluations(harness, quality):
    """Pair harness and plan-quality results that scored the same plans.

    Returns:
        (harness file, harness doc, quality file, quality doc) tuples; either
        half is None when a file has no partner. If several files of one kind
        scored the same plans, the newest is paired and the rest stand alone.
    """
    unpaired_quality = _newest_first(quality)
    out = []
    for h_name, h_doc in _newest_first(harness):
        key = _pair_key(h_doc)
        match = next(
            (q for q in unpaired_quality if key and _pair_key(q[1]) == key), None
        )
        if match:
            unpaired_quality.remove(match)
            out.append((h_name, h_doc, match[0], match[1]))
        else:
            out.append((h_name, h_doc, None, None))
    out += [(None, None, q_name, q_doc) for q_name, q_doc in unpaired_quality]
    return out


def build(results_dir: pathlib.Path) -> tuple[list[dict], list[str]]:
    """Load every results file in `results_dir` as evaluations, newest first.

    Each evaluation is one harness results file, one plan-quality results file,
    or a pair of them that scored the same plans.

    Returns:
        The evaluations to embed, and the names of files skipped with the reason.
    """
    harness, quality, skipped = _load_results(results_dir)
    runs = []
    for h_name, h_doc, q_name, q_doc in _evaluations(harness, quality):
        try:
            profiles = _profile_context(h_doc, q_doc, results_dir)
        except (OSError, json.JSONDecodeError, KeyError) as e:
            print(
                f"warning: {h_name or q_name}: no profile details ({e})",
                file=sys.stderr,
            )
            profiles = {}
        runs.append(
            {
                "file": h_name or q_name,
                "quality_file": q_name,
                "result": h_doc or {},
                "quality": q_doc,
                "profiles": profiles,
                "generated_at": max(
                    (d.get("generated_at", "") for d in (h_doc, q_doc) if d), default=""
                ),
            }
        )
    runs.sort(key=lambda r: r["generated_at"], reverse=True)
    return runs, skipped


def render(runs: list[dict]) -> str:
    """Embed `runs` in the dashboard template."""
    # Escape "</" so a rationale containing "</script>" cannot end the block.
    payload = json.dumps(runs, ensure_ascii=False).replace("</", "<\\/")
    return TEMPLATE.read_text().replace("__DASHBOARD_DATA__", payload)


def main(argv=None) -> int:
    """Write the dashboard HTML."""
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument(
        "results_dir",
        nargs="?",
        default=str(HERE / "data" / "results"),
        help="Directory of results files (default: data/results)",
    )
    ap.add_argument(
        "-o",
        "--out",
        help="Output HTML file (default: dashboard.html in the results directory)",
    )
    args = ap.parse_args(argv)

    results_dir = pathlib.Path(args.results_dir)
    runs, skipped = build(results_dir)
    for s in skipped:
        print(f"skipped {s}", file=sys.stderr)
    if not runs:
        sys.exit(f"error: no harness or plan-quality results files in {results_dir}")

    out = pathlib.Path(args.out) if args.out else results_dir / "dashboard.html"
    out.write_text(render(runs))
    names = [
        r["file"]
        + (f" + {r['quality_file']}" if r["quality_file"] and r["result"] else "")
        for r in runs
    ]
    print(f"wrote {out} ({len(runs)} evaluation(s): {', '.join(names)})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
