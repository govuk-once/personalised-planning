"""Build a single-file HTML dashboard over the metrics harness's results files.

Reads every `results*.json` written by `metrics.harness score` in a directory,
adds each scored profile's situation, readable answers and weight from the
profiles file the run recorded, and embeds the lot in one HTML page with a
dropdown to switch between runs. The page needs no server or network: open it
straight from disk. Re-run this script after a new `score` run to pick it up.

Files in other formats (`truth.py score` results, review packets) are skipped
with a note, since they carry different metrics.

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


def _resolve(path: str | None) -> pathlib.Path | None:
    """Find a profiles file recorded in a run's config, even if the repo moved.

    The harness records absolute paths, so fall back to the same file name under
    `data/profiles/` when the recorded path no longer exists.
    """
    if not path:
        return None
    p = pathlib.Path(path)
    if p.is_file():
        return p
    fallback = HERE / "data" / "profiles" / p.name
    return fallback if fallback.is_file() else None


def _profile_context(doc: dict) -> dict[str, dict]:
    """Situation, readable answers and weight for each profile the run scored."""
    config = doc.get("config", {})
    path = _resolve(config.get("weights_file")) or _resolve(config.get("profiles_file"))
    if path is None:
        return {}
    data = json.loads(path.read_text())
    profiles = data["profiles"] if isinstance(data, dict) else data
    scored = {
        pid
        for key in METRIC_KEYS
        for pid in (doc.get(key) or {}).get("per_profile", {})
    }
    return {
        p["id"]: {
            "situation": p.get("situation"),
            "readable": p.get("readable", {}),
            "weight": p.get("weight"),
        }
        for p in profiles
        if p.get("id") in scored
    }


def build(results_dir: pathlib.Path) -> tuple[list[dict], list[str]]:
    """Load every harness results file in `results_dir`, newest run first.

    Returns:
        The runs to embed, and the names of files skipped with the reason.
    """
    runs, skipped = [], []
    for path in sorted(results_dir.glob("*.json")):
        try:
            doc = json.loads(path.read_text())
        except (OSError, json.JSONDecodeError) as e:
            skipped.append(f"{path.name} (unreadable: {e})")
            continue
        if not _is_harness_result(doc):
            skipped.append(f"{path.name} (not a metrics.harness results file)")
            continue
        try:
            profiles = _profile_context(doc)
        except (OSError, json.JSONDecodeError, KeyError) as e:
            print(f"warning: {path.name}: no profile details ({e})", file=sys.stderr)
            profiles = {}
        runs.append({"file": path.name, "result": doc, "profiles": profiles})
    runs.sort(key=lambda r: r["result"].get("generated_at", ""), reverse=True)
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
        sys.exit(f"error: no metrics.harness results files in {results_dir}")

    out = pathlib.Path(args.out) if args.out else results_dir / "dashboard.html"
    out.write_text(render(runs))
    print(f"wrote {out} ({len(runs)} run(s): {', '.join(r['file'] for r in runs)})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
