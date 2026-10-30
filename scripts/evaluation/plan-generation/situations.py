"""Add a first-person `situation` sentence to every profile.

    python situations.py data/driving_profiles_v5.json data/situations_v5.json

The planner is sent a `situation` alongside the user's context. In production
it is a one-sentence summary of what the person wants help with. Here it is
chosen from the profile's answer to one question (the templates file's
`question`), so every profile states what it actually wants rather than a
single hard-coded string.

The profiles file is rewritten in place with `situation` placed after `id`.
Nothing else in a profile changes, so ground truth stays valid. Running it
again overwrites `situation`. If any profile has no template, nothing is
written.
"""

import argparse
import json
import os
import pathlib
import sys


def load(path):
    """Read a JSON file."""
    resolved = pathlib.Path(path).resolve()
    if not resolved.is_file():
        raise ValueError(f"Not a valid file path: {path}")
    return json.loads(resolved.read_text())


def add_situation(profile, question, situations):
    """Return a copy of the profile with `situation` set after `id`.

    Args:
        profile: A synthetic profile record.
        question: Id of the question whose answer picks the template.
        situations: Answer id mapped to situation sentence.

    Returns:
        The profile with `situation`, or None if its answer has no template.
    """
    situation = situations.get(profile.get("answers", {}).get(question))
    if not situation:
        return None
    rest = {k: v for k, v in profile.items() if k not in ("id", "situation")}
    return {"id": profile["id"], "situation": situation, **rest}


def main(argv=None):
    """Entry point."""
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("profiles", help="profiles file, rewritten in place")
    ap.add_argument("situations", help="templates file")
    args = ap.parse_args(argv)

    data, templates = load(args.profiles), load(args.situations)
    question, situations = templates["question"], templates["situations"]

    updated, missing = [], []
    for profile in data["profiles"]:
        result = add_situation(profile, question, situations)
        if result is None:
            missing.append(profile.get("id", "?"))
        else:
            updated.append(result)
    if missing:
        print(
            f"error: no situation for {len(missing)} profile(s) "
            f"(answer to {question} has no template): {', '.join(missing)}",
            file=sys.stderr,
        )
        return 1

    out = pathlib.Path(args.profiles).resolve()
    tmp = out.with_name(out.name + ".tmp")
    tmp.write_text(json.dumps({**data, "profiles": updated}, indent=2, default=str))
    os.replace(tmp, out)
    print(f"added situation to {len(updated)} profiles", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
