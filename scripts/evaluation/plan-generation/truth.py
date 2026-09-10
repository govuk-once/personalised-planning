"""Ground-truth plans from a GOV.UK step by step, for any life event.

    python truth.py map data/model.json --url https://www.gov.uk/learn-to-drive-a-car
    python truth.py map data/model.json --urls-file guides.txt > data/mapping.json
    python truth.py build data/profiles.json data/model.json data/mapping.json > data/truth.json
    python truth.py score app_plans.json data/truth.json

Guides are named by URL and read live from the GOV.UK content API, so what
you map is what is published rather than whatever a subgraph snapshot last
captured. Several can be mapped at once, each producing its own mapping.

The mapping carries its own copy of the steps, so nothing downstream needs
the subgraph or the network.

A step by step is already a plan — an ordered set of steps authored and
editorially approved by GDS. Ground truth is that spine with each step marked
required, not_required or blocked for one person. Anchoring to a hand-authored
spine is what stops this being one model's prose judged against another's.

`map` is the only stage that calls a model, and it runs ONCE per life event
rather than once per profile. It produces a mapping of perhaps fifteen lines:
which fact decides each step, which answers block which steps, and who the
guide is for. A person can check that in a sitting. `build` then applies it in
pure code, so a thousand ground truths inherit one reviewed judgement instead
of a thousand unreviewed ones.

The mapping cannot be inferred. Fact polarity has no reliable convention: in
the driving model `theory_ahead=true` means the theory steps apply, while
`theory_exempt=true` means they do not — same shape, opposite meaning. Shared
content paths between a fact and a step show the two are related but not which
way round, so that overlap is passed to the mapping stage as a hint and
nothing more.
"""

import json
import pathlib
import sys
from urllib.parse import urlsplit

from prompts import MAP_SYSTEM, MAP_TOOL

MODEL = "eu.anthropic.claude-sonnet-5"


# --------------------------------------------------------------------------
# spines
# --------------------------------------------------------------------------


def parse_nav(nav):
    """Turn a step_by_step_nav block into an ordered step list.

    Args:
        nav: The `step_by_step_nav` object from a page's details.

    Returns:
        A list of steps, each with a number, title, intro text and outbound
        links.
    """
    steps = []
    for i, step in enumerate(nav.get("steps", []), 1):
        links, paras = [], []
        for block in step.get("contents", []):
            if block.get("type") == "list":
                # Drop entries with no href: a link with nowhere to go is
                # not a citation, and a None in this list becomes a null in
                # the mapping's stored spine.
                links += [
                    it["href"] for it in block.get("contents", []) if it.get("href")
                ]
            elif block.get("text"):
                paras.append(block["text"])
        steps.append(
            {
                "step": i,
                "title": step.get("title"),
                "intro": " ".join(paras),
                "links": links,
            }
        )
    return steps


def api_url(url):
    """Turn any GOV.UK step-by-step reference into its content API address.

    The published HTML page and the API return the same underlying content,
    but the API returns it as JSON with the step structure intact, so there
    is no scraping and no dependence on page markup.

    Args:
        url: A full URL, a bare host-and-path, or just a path.

    Returns:
        The content API URL for that page.

    Raises:
        ValueError: If the reference is empty, or names a host other than
            GOV.UK. A non-GOV.UK URL is rejected rather than reinterpreted
            as a path, which would silently fetch the wrong page.
    """
    text = url.strip()
    # urlsplit only finds a host after a scheme, so add one for bare
    # references like "www.gov.uk/x". A dot in the first segment is what
    # distinguishes those from a lone slug like "learn-to-drive-a-car",
    # which is already a path.
    if "://" not in text and "." in text.split("/")[0]:
        text = "//" + text
    parts = urlsplit(text, scheme="https")

    if parts.scheme not in ("http", "https"):
        raise ValueError(f"{url!r}: only http(s) URLs are supported")
    host = parts.hostname or ""
    if host and host not in ("www.gov.uk", "gov.uk"):
        raise ValueError(f"{url!r}: not a GOV.UK address")

    # The query and fragment address the HTML page, not the API; passing
    # them through yields a 404 or an unexpected document. urlsplit has
    # already separated them out.
    path = "/" + "/".join(part for part in parts.path.split("/") if part)
    if path == "/":
        raise ValueError(f"{url!r}: no page named")
    if path.startswith("/api/content/"):
        return "https://www.gov.uk" + path
    return "https://www.gov.uk/api/content" + path


def fetch_spine(url, opener=None):
    """Read a step by step straight from GOV.UK.

    Args:
        url: A URL or path for the step-by-step page.
        opener: Optional callable taking a URL and returning JSON text, for
            testing without network access.

    Returns:
        A tuple of (base_path, steps).

    Raises:
        ValueError: If the page is not a step by step.
    """
    import urllib.request

    target = api_url(url)
    if opener is None:

        def opener(u):
            request = urllib.request.Request(
                u, headers={"User-Agent": "ground-truth-builder"}
            )
            with urllib.request.urlopen(request, timeout=30) as response:
                return response.read().decode()

    content = json.loads(opener(target))
    nav = (content.get("details") or {}).get("step_by_step_nav")
    if not nav:
        raise ValueError(
            f"{target} is not a step by step "
            f"(document_type={content.get('document_type')!r})"
        )
    steps = parse_nav(nav)
    if not steps:
        raise ValueError(f"{target} has no steps")
    # Fall back to the path rather than the full API address, so the
    # mapping is keyed the same way whether or not the page declares one.
    path = content.get("base_path") or target.split("/api/content", 1)[-1]
    return path, steps


# --------------------------------------------------------------------------
# map
# --------------------------------------------------------------------------


def build_mapping(client, path, steps, model):
    """Ask a model to map one spine onto the questionnaire.

    Args:
        client: A boto3 bedrock-runtime client.
        path: base_path of the step by step.
        steps: Its spine, from `spines`.
        model: The elicitation model.

    Returns:
        A mapping holding rules, blocks and optionally scope.

    Raises:
        RuntimeError: If the model replied without calling the tool.
    """
    # No "which facts relate to which step" hint is supplied. One was tried,
    # derived from facts and steps citing the same pages, and removed: on the
    # driving guide it identified the right fact for one rule in four and
    # suggested `theory_exempt` where the answer was `theory_ahead` — a
    # plausible-looking wrong hint on exactly the polarity axis the prompt
    # warns about. Shared pages show two things are related, never which way
    # the fact points.
    brief = {
        "guide": path,
        "steps": steps,
        "facts": [
            {"id": f["id"], "description": f.get("description", "")}
            for f in model.get("facts", [])
        ],
        "questions": [
            {
                "id": q["id"],
                "text": q["text"],
                "ask_if": q.get("ask_if"),
                "options": [o["id"] for o in q["options"]],
                "blocker_type": q.get("blocker_type"),
            }
            for q in model.get("questions", [])
        ],
    }
    response = client.converse(
        modelId=MODEL,
        inferenceConfig={"maxTokens": 8000},
        system=[{"text": MAP_SYSTEM}],
        messages=[{"role": "user", "content": [{"text": json.dumps(brief, indent=1)}]}],
        toolConfig={
            "tools": [
                {
                    "toolSpec": {
                        "name": MAP_TOOL["name"],
                        "inputSchema": {"json": MAP_TOOL["input_schema"]},
                    }
                }
            ],
            "toolChoice": {"tool": {"name": MAP_TOOL["name"]}},
        },
    )
    for block in response["output"]["message"]["content"]:
        if "toolUse" in block:
            return {"step_by_step": path, **block["toolUse"]["input"]}
    raise RuntimeError(
        f"model did not return a mapping; stop_reason={response.get('stopReason')}"
    )


def check_mapping(mapping, steps, model):
    """Validate a mapping before it is applied to every profile.

    A mapping is small and applied silently to thousands of records, so a
    reference to a fact, question or step that does not exist would fail
    invisibly rather than loudly.

    Args:
        mapping: A mapping from `build_mapping`.
        steps: The spine it describes.
        model: The elicitation model.

    Returns:
        Error strings, empty if the mapping is sound.
    """
    errs = []
    facts = {f["id"] for f in model.get("facts", [])}
    questions = {
        q["id"]: {o["id"] for o in q["options"]} for q in model.get("questions", [])
    }
    text_to_id = {q.get("text"): q["id"] for q in model.get("questions", [])}
    numbers = {s["step"] for s in steps}

    def check_answers(where, qid, answers):
        """Verify a question exists and the answers named are real options."""
        if qid not in questions:
            hint = text_to_id.get(qid)
            if hint:
                return [
                    f"{where}: '{qid}' is a question's text, not its id — use '{hint}'"
                ]
            return [f"{where}: unknown question '{qid}'"]
        return [
            f"{where}: '{a}' is not an option of {qid}"
            for a in answers or []
            if a not in questions[qid]
        ]

    seen = [r["step"] for r in mapping.get("rules", [])]
    for rule in mapping.get("rules", []):
        has_fact, has_question = "fact" in rule, "question" in rule
        if has_fact and has_question:
            errs.append(
                f"rule for step {rule['step']}: has both 'fact' and "
                f"'question' — use exactly one form"
            )
        elif has_fact:
            if rule["fact"] not in facts:
                errs.append(
                    f"rule for step {rule['step']}: unknown fact '{rule['fact']}'"
                )
            if not isinstance(rule.get("drop_when"), bool):
                errs.append(
                    f"rule for step {rule['step']}: fact-form rule needs a "
                    f"boolean 'drop_when'"
                )
        elif has_question:
            errs += check_answers(
                f"rule for step {rule['step']}",
                rule.get("question"),
                rule.get("answers"),
            )
            if not rule.get("answers"):
                errs.append(
                    f"rule for step {rule['step']}: question-form rule needs 'answers'"
                )
        else:
            errs.append(f"rule for step {rule['step']}: needs 'fact' or 'question'")
        if rule["step"] not in numbers:
            errs.append(f"rule references step {rule['step']}, which does not exist")
    for n in sorted({s for s in seen if seen.count(s) > 1}):
        errs.append(f"step {n} has more than one rule")

    for block in mapping.get("blocks", []):
        qid = block["question"]
        errs += check_answers("block", qid, block.get("answers"))
        if not block.get("steps"):
            errs.append(
                f"block on {qid}={block.get('answers')} blocks no steps — a "
                f"block with an empty 'steps' list does nothing; if this "
                f"question decides who the guide is for, it belongs in "
                f"'scope', not 'blocks'"
            )
        errs += [
            f"block on {qid} references step {n}, which does not exist"
            for n in block.get("steps", [])
            if n not in numbers
        ]

    for cond in mapping.get("scope") or []:
        errs += check_answers("scope", cond.get("question"), cond.get("answers"))
    return errs


# --------------------------------------------------------------------------
# build
# --------------------------------------------------------------------------


def rule_drops(rule, answers, model, resolve):
    """Decide whether a rule drops its step for one person, either form.

    Fact-form and question-form rules ask different questions of the
    profile — a resolved derived fact, or a raw answer against a list — but
    both boil down to one boolean plus a reason a reviewer can check.

    Args:
        rule: One rule, fact-form (`fact`, `drop_when`) or question-form
            (`question`, `answers`, optional `exclude`).
        answers: One profile's answers.
        model: The elicitation model, for the fact resolver.
        resolve: The elicitation model's fact resolver.

    Returns:
        A (drop, why) pair.
    """
    if "fact" in rule:
        drop = resolve(model, rule["fact"], answers) == rule["drop_when"]
        return drop, f"{rule['fact']}={str(rule['drop_when']).lower()}"
    given = answers.get(rule["question"])
    matches = given in set(rule.get("answers") or [])
    drop = matches == bool(rule.get("exclude"))
    return drop, f"{rule['question']}={given!r}"


def verdicts(model, steps, answers, mapping, resolve):
    """Mark each step required, not_required or blocked for one person.

    Args:
        model: The elicitation model.
        steps: The spine.
        answers: One profile's answers.
        mapping: The reviewed mapping for this spine.
        resolve: The elicitation model's fact resolver.

    Returns:
        One verdict per step, each naming what decided it.
    """
    blocked = {}
    for block in mapping.get("blocks", []):
        if answers.get(block["question"]) in set(block["answers"]):
            for n in block["steps"]:
                blocked.setdefault(n, block["why"])
    rules = {r["step"]: r for r in mapping.get("rules", [])}

    out = []
    for step in steps:
        n = step["step"]
        rule = rules.get(n)
        drop, why = rule_drops(rule, answers, model, resolve) if rule else (False, "")
        if n in blocked:
            out.append(
                {
                    "step": n,
                    "title": step["title"],
                    "verdict": "blocked",
                    "why": blocked[n],
                }
            )
        elif rule and drop:
            out.append(
                {
                    "step": n,
                    "title": step["title"],
                    "verdict": "not_required",
                    "why": why,
                }
            )
        else:
            out.append(
                {
                    "step": n,
                    "title": step["title"],
                    "verdict": "required",
                    "why": "decided by a rule that did not drop this step"
                    if rule
                    else "applies to everyone",
                }
            )
    return out


def in_scope(profile, mapping):
    """Whether this guide covers this person.

    Scope is a list because narrowing to a route is rarely enough on its own.
    The driving guide covers cars, but also only Great Britain — Northern
    Ireland is served by a different body — so it needs one condition to
    include and one to exclude.

    Args:
        profile: A profile record.
        mapping: The reviewed mapping.

    Returns:
        True if the profile satisfies every scope condition, or the guide
        covers everyone.
    """
    for cond in mapping.get("scope") or []:
        given = profile["answers"].get(cond["question"])
        matches = given in set(cond["answers"])
        if matches == bool(cond.get("exclude")):
            return False
    return True


def unreachable_conditions(profiles, mapping):
    """Flag rules and blocks keyed on a question no in-scope profile reaches.

    A rule or block can only ever apply to someone who was asked the question
    it keys on. If scope excludes everyone whose answers would reach that
    question — a car-learner guide keying a block on a question only asked
    when applying for a first provisional, say — the rule or block is dead,
    and worse, misleading: it looks like it personalises the plan but never
    runs for anyone the guide covers. The profile set encodes reachability
    directly, since a question a profile was never asked has no answer for it,
    so this reads against the profiles rather than reasoning about ask_if.

    Args:
        profiles: All profiles, unscoped; scope is applied here.
        mapping: The reviewed mapping.

    Returns:
        Error strings, one per rule or block whose question is unreachable.
    """
    scoped = [p for p in profiles if in_scope(p, mapping)]

    def reached(qid):
        return any(p["answers"].get(qid) is not None for p in scoped)

    out = []
    for rule in mapping.get("rules", []):
        qid = rule.get("question")
        if qid and not reached(qid):
            out.append(
                f"rule for step {rule['step']} keys on '{qid}', which no "
                f"in-scope profile is ever asked — unreachable under this scope"
            )
    for block in mapping.get("blocks", []):
        qid = block["question"]
        if not reached(qid):
            out.append(
                f"block on '{qid}' keys on a question no in-scope profile is "
                f"ever asked — unreachable under this scope"
            )
    return out


def degenerate_blocks(profiles, mapping):
    """Flag blocks that fire for all, or none, of the in-scope profiles.

    A block marks a step a person is legally barred from, so it must divide
    the people the guide covers: some barred, some not. A block that fires
    for everyone in scope shuts a step out of every plan — the signature of
    a sequencing prerequisite ("you need a provisional first") mistaken for
    a personal gate, since no one has completed earlier steps yet. Those
    steps are still relevant, and `score` will charge an app for showing
    them. A block whose question is reached but whose answers never match
    does nothing at all. A block whose question is never reached is left to
    `unreachable_conditions`, so it is not double-reported here.

    Args:
        profiles: All profiles, unscoped; scope is applied here.
        mapping: The reviewed mapping.

    Returns:
        Warning strings, one per degenerate block.
    """
    scoped = [p for p in profiles if in_scope(p, mapping)]
    out = []
    for block in mapping.get("blocks", []):
        answers = set(block["answers"])
        fires = sum(1 for p in scoped if p["answers"].get(block["question"]) in answers)
        reached = sum(
            1 for p in scoped if p["answers"].get(block["question"]) is not None
        )
        where = (
            f"block on {block['question']}={block['answers']} (steps {block['steps']})"
        )
        if scoped and fires == len(scoped):
            out.append(
                f"{where} fires for all {len(scoped)} in-scope profiles: likely "
                f"a sequencing prerequisite, not a legal gate — those steps are "
                f"probably relevant and should stay in the plan"
            )
        elif reached and not fires:
            out.append(f"{where} fires for no in-scope profile: it does nothing")
    return out


# --------------------------------------------------------------------------
# score
# --------------------------------------------------------------------------


def score(plan, truth):
    """Compare one generated plan against its ground truth.

    Args:
        plan: A plan record with `profile_id` and a `steps` list.
        truth: The matching ground-truth record.

    Returns:
        What was missed, added, or presented despite being blocked, plus F1.
    """
    want = {v["step"] for v in truth["verdicts"] if v["verdict"] == "required"}
    stop = {v["step"] for v in truth["verdicts"] if v["verdict"] == "blocked"}
    got = set(plan.get("steps") or [])
    hit = len(want & got)

    if not want and not got:
        # Presenting nothing when nothing is required is correct, not a
        # failure. Scoring this 0.0 would penalise an app precisely on the
        # profiles where every step is blocked — the cases most worth
        # getting right.
        p = r = 1.0
    else:
        p = hit / len(got) if got else 0.0
        r = hit / len(want) if want else 0.0
    return {
        "profile_id": truth["profile_id"],
        "missing": sorted(want - got),
        "extra": sorted(got - want - stop),
        "blocked_but_present": sorted(stop & got),
        "precision": round(p, 3),
        "recall": round(r, 3),
        "f1": round(2 * p * r / (p + r), 3) if p + r else 0.0,
    }


# --------------------------------------------------------------------------


def load(*paths):
    """Read several JSON files.

    Args:
        *paths: File paths.

    Returns:
        The parsed contents, in order.
    """
    return [json.loads(pathlib.Path(p).read_text()) for p in paths]


def read_urls(path):
    """Read step-by-step URLs from a text file, one per line.

    Blank lines and lines starting with # are ignored, so the file can carry
    notes about which guide is which and why one is commented out.

    Args:
        path: Path to the text file.

    Returns:
        The URLs, in file order.
    """
    lines = pathlib.Path(path).read_text().splitlines()
    return [
        line.strip()
        for line in lines
        if line.strip() and not line.strip().startswith("#")
    ]


def collect_spines(urls, opener=None):
    """Fetch every named step by step.

    A URL that fails is reported and skipped rather than aborting the run: a
    typo in one line of a URL file should not throw away the guides that
    fetched cleanly.

    Args:
        urls: Step-by-step URLs or paths.
        opener: Optional callable for fetching, for testing offline.

    Returns:
        A tuple of (spines keyed by base_path, list of failure messages).
    """
    found, failures = {}, []
    for url in urls:
        try:
            path, steps = fetch_spine(url, opener)
        except (OSError, ValueError, json.JSONDecodeError) as exc:
            failures.append(f"{url}: {type(exc).__name__}: {exc}")
            continue
        if path in found:
            failures.append(f"{url}: {path} was already fetched, skipping")
            continue
        found[path] = steps
        print(f"fetched {path} ({len(steps)} steps)", file=sys.stderr)
    return found, failures


def cmd_map(args):
    """Generate and validate a mapping per step by step.

    The mapping carries its own copy of the spine, so `build` needs no
    subgraph and works identically whether the guide came from a file or
    from GOV.UK.

    Args:
        args: Parsed arguments holding model, subgraph, url and region.

    Returns:
        Exit code; 1 if any mapping failed validation or none was found.
    """
    model = load(args.model)[0]
    if not model.get("facts"):
        print(
            "warning: model has no facts — every step rule must key on a single "
            "question, which cannot express a step whose relevance combines "
            "several answers; such steps will be silently mis-mapped or omitted. "
            "Consider regenerating the model with derived facts.",
            file=sys.stderr,
        )
    urls = list(args.url or [])
    if args.urls_file:
        urls += read_urls(args.urls_file)

    found, failures = collect_spines(urls)
    for f in failures:
        print(f"  {f}", file=sys.stderr)
    if not found:
        print("no step by step could be fetched", file=sys.stderr)
        return 1

    # Imported here rather than at the top so the checks above can fail
    # helpfully on a machine with no Bedrock credentials or SDK installed.
    import boto3

    client = boto3.client("bedrock-runtime", region_name=args.region)
    mappings, failed = [], 0
    for path, steps in found.items():
        mapping = build_mapping(client, path, steps, model)
        mapping["rules"] = [
            r for r in mapping.get("rules", []) if "fact" in r or "question" in r
        ]
        errs = check_mapping(mapping, steps, model)
        mapping["validation"] = errs or "clean"
        mapping["spine"] = steps
        failed += bool(errs)
        for e in errs:
            print(f"  {path}: {e}", file=sys.stderr)
        mappings.append(mapping)
        print(
            f"{path}: {len(mapping.get('rules', []))} rules, "
            f"{len(mapping.get('blocks', []))} blocks",
            file=sys.stderr,
        )
    print(json.dumps({"mappings": mappings}, indent=2))
    print(
        "REVIEW THIS MAPPING BEFORE BUILDING — it is applied silently to every profile",
        file=sys.stderr,
    )
    return 1 if (failed or failures) else 0


def cmd_build(args):
    """Apply reviewed mappings to every profile, in pure code.

    Args:
        args: Parsed arguments holding profiles, model, mapping and an
            optional subgraph.

    Returns:
        Exit code; 1 if a mapping has no spine and none can be found.
    """
    sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
    from plans import resolve

    profiles, model, mapping_file = load(args.profiles, args.model, args.mapping)

    truths, failed = [], False
    for mapping in mapping_file["mappings"]:
        path = mapping["step_by_step"]
        steps = mapping.get("spine")
        if not steps:
            print(f"{path}: mapping has no spine. Re-run map.", file=sys.stderr)
            return 1
        # Re-validate here rather than trusting the mapping's stored
        # `validation` field: a mapping can be hand-edited after `map` wrote
        # it, and a wrong mapping is applied silently to every profile. The
        # reachability and degeneracy checks need the profile set, so they
        # can only run at build; folding the structural check in too means
        # one gate refuses every kind of broken mapping.
        errs = check_mapping(mapping, steps, model)
        errs += unreachable_conditions(profiles["profiles"], mapping)
        errs += degenerate_blocks(profiles["profiles"], mapping)
        if errs:
            for e in errs:
                print(f"  {path}: {e}", file=sys.stderr)
            failed = True
            continue
        scoped = [p for p in profiles["profiles"] if in_scope(p, mapping)]
        print(
            f"{path}: {len(scoped)} of {len(profiles['profiles'])} profiles in scope",
            file=sys.stderr,
        )
        truths += [
            {
                "profile_id": p["id"],
                "step_by_step": path,
                "verdicts": verdicts(model, steps, p["answers"], mapping, resolve),
            }
            for p in scoped
        ]

    if failed:
        print(
            "build aborted: a mapping did not validate. Fix it (or re-run map) "
            "and build again — no ground truth was written.",
            file=sys.stderr,
        )
        return 1

    print(
        json.dumps(
            {
                "meta": {
                    "profiles": len(truths),
                    "guides": [m["step_by_step"] for m in mapping_file["mappings"]],
                },
                "spines": {
                    m["step_by_step"]: m["spine"] for m in mapping_file["mappings"]
                },
                "truths": truths,
            },
            indent=2,
        )
    )
    return 0


def cmd_score(args):
    """Score generated plans against ground truth.

    Args:
        args: Parsed arguments holding the app's plans and the ground truth.

    Returns:
        Exit code; 0 on success.
    """
    app, truth = load(args.plans, args.truth)
    # Compound key: a profile can appear in multiple guides, and a plain
    # profile_id dict would silently overwrite the earlier guide's verdicts.
    by_key = {(t["profile_id"], t["step_by_step"]): t for t in truth["truths"]}
    profiles_with_truth = {pid for pid, _ in by_key}

    plans = app.get("plans", [])
    matched = [p for p in plans if p.get("profile_id") in profiles_with_truth]

    # A total mismatch otherwise reports mean_f1 0.0, which reads as a broken
    # app rather than as two files that do not refer to the same profiles.
    for count, ids, note in [
        (
            len(plans) - len(matched),
            [
                p.get("profile_id")
                for p in plans
                if p.get("profile_id") not in profiles_with_truth
            ],
            "have no matching ground truth",
        ),
        (
            sum(1 for p in matched if "steps" not in p),
            [p.get("profile_id") for p in matched if "steps" not in p],
            "have no 'steps' key and are scored as empty",
        ),
    ]:
        if count:
            print(f"warning: {count} plan(s) {note}, e.g. {ids[:3]}", file=sys.stderr)
    if not matched:
        print(
            "no plans matched the ground truth — check that profile_id values line up",
            file=sys.stderr,
        )
        return 1

    # Score each (profile, guide) pair; a profile in two guides gets two scores.
    # Plans carry step_by_step (written by run_app), so look up truth directly.
    scores = [
        {
            **score(p, by_key[(p["profile_id"], p["step_by_step"])]),
            "step_by_step": p["step_by_step"],
        }
        for p in matched
        if (p.get("profile_id"), p.get("step_by_step")) in by_key
    ]
    n = len(scores)
    print(
        json.dumps(
            {
                "summary": {
                    "profiles": len(scores),
                    "plans_without_ground_truth": len(plans) - len(matched),
                    "mean_f1": round(sum(s["f1"] for s in scores) / n, 3),
                    "perfect": sum(
                        1
                        for s in scores
                        if s["f1"] >= 1.0 and not s["blocked_but_present"]
                    ),
                    "presented_a_blocked_step": sum(
                        1 for s in scores if s["blocked_but_present"]
                    ),
                    "missed_a_required_step": sum(1 for s in scores if s["missing"]),
                },
                "scores": scores,
            },
            indent=2,
        )
    )
    return 0


def main(argv=None):
    """Entry point.

    Args:
        argv: Argument list, or None to read from sys.argv.

    Returns:
        Exit code.
    """
    import argparse

    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    sub = ap.add_subparsers(dest="command", required=True)

    m = sub.add_parser("map", help="work out which fact decides each step")
    m.add_argument("model", help="elicitation model JSON")
    m.add_argument(
        "--url",
        action="append",
        metavar="URL",
        help="a GOV.UK step by step, e.g. "
        "https://www.gov.uk/learn-to-drive-a-car. Repeatable.",
    )
    m.add_argument(
        "--urls-file",
        metavar="FILE",
        help="text file of step-by-step URLs, one per line. "
        "Blank lines and # comments are ignored.",
    )
    m.add_argument("--region", default="eu-west-2")
    m.set_defaults(fn=cmd_map)

    b = sub.add_parser("build", help="apply a reviewed mapping to every profile")
    b.add_argument("profiles")
    b.add_argument("model")
    b.add_argument("mapping")
    b.set_defaults(fn=cmd_build)

    s = sub.add_parser("score", help="compare generated plans to ground truth")
    s.add_argument("plans")
    s.add_argument("truth")
    s.set_defaults(fn=cmd_score)

    args = ap.parse_args(argv)
    if args.command == "map" and not args.url and not args.urls_file:
        ap.error("map needs --url or --urls-file")
    return args.fn(args)


if __name__ == "__main__":
    sys.exit(main())
