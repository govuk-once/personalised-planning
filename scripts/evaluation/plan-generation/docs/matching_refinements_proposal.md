# Proposal: refining how plans are matched to ground truth

**Scope:** plan-generation evaluation (`scripts/evaluation/plan-generation`), all life events
**Status:** draft for discussion
**Evidence base:** Having a Baby, 38 heaviest profiles × 3 plans (quality and auto-eval runs, 17 Nov 2026)

---

## 1. Summary

Step precision and recall depend on how each task in a generated plan is matched to a step in the GOV.UK step-by-step spine. In the Having a Baby run, a large share of the reported errors came from the matcher, not from the plans. Correcting for the matcher alone moves weighted precision from 0.87 to up to 1.00, and recall from 0.60 to 0.63.

The underlying causes are not specific to Having a Baby:

- several steps link to the same GOV.UK page
- the matcher ignores the person's situation
- ground truth has no notion of time: a step is either required or not, with no way to say "not yet" or "no longer".

This proposal sets out four refinements. Each one is configured per life event in the mapping or spine, not hard-coded. The last one models **state transitions**: answers that are expected to change over time, such as a baby being born or a residency period being reached. Steps that are blocked now but will apply later get a new `deferred` verdict, and steps whose window has passed get an `expired` verdict.

The scoring path stays deterministic. No LLM is added, and the agent itself doesn't change.

---

## 2. How matching works today

1. `truth.py map` produces a reviewed mapping per step by step: rules and blocks over profile answers.
2. `truth.py build` gives each step a verdict for each profile: `required`, `not_required`, `optional` or `blocked`.
3. `run_app.py match_task()` maps each plan task to spine steps by `gov_service_url`:
   - A URL linked from one step decides that step (`url`). A sub-page counts as its parent.
   - A URL linked from several steps credits every step whose `match_terms` appear in the task title (`terms`).
   - If no terms appear, the task credits the earliest of those steps (`fallback`).
   - A URL linked from no step is `unmatched` and doesn't affect the score.
4. `truth.py score()` compares the set of covered steps with the verdicts, giving precision, recall and F1. Optional steps are neutral.

---

## 3. Problems addressed, and how they generalise

| # | Problem | Having a Baby evidence | Why it generalises |
|---|---|---|---|
| P1 | **Several steps link to the same page.** One page, such as a benefit or entitlement page, is linked from several stages: check, give notice, take or claim. | The maternity and paternity pay pages are linked from steps 1, 2, 3 and 7. | Step-by-steps routinely link one service page from each stage of using it. Driving does this for the licence and test pages. |
| P2 | **Matching depends on verbs.** `match_terms` include words like "claim", and the agent's `Task.title` must start with a verb (`agent/app/structured_outputs.py`). | The same maternity pay task lands on step 1, 3 or 7 depending only on its first word. | Every life event uses the same task schema, so title verbs are an arbitrary signal everywhere. |
| P3 | **A task counts as a hit and an extra at once.** `extra` refers to a shown step that isn't required, i.e. `not_required` or `blocked`. A task matching several steps credits all of them, including steps that don't apply. | "Claim Statutory Paternity Pay" covers step 7 (needed) and step 2 (often not needed). That causes 44 of the 59 extras. | It happens wherever a shared page spans steps with different verdicts. |
| P4 | **Matching ignores the person's situation.** The matcher never sees the profile. | 14 maternity pay tasks for mothers whose baby is already born were matched only to step 3 (give notice), which no longer applies. Each one counted as an extra and a miss. | Any step that only applies before or after an event is affected. |
| P5 | **Verdicts ignore time.** A step is `required`, `not_required` or `blocked` for the profile's current answers only. | Giving notice is `not_required` once the baby is born; it has lapsed, not become irrelevant. | Driving: some steps are blocked until the person meets the UK residency condition. They are not irrelevant, just not yet available. |

---

## 4. Design principles

1. **Deterministic scoring.** Keep LLMs out of the step-scoring path, as `run_app.py` already does.
2. **Configure in data, not code.** Anything specific to a life event lives in the spine or mapping, reviewed once per life event, in line with the current `map` → review → `build` flow.
3. **Never add coverage the URL doesn't support.** The refinements only choose between, or remove, steps that a task already matched by URL.
4. **Show raw and refined side by side.** Report the current ("raw") scores alongside the refined ones, so changes to the measurement are never mistaken for changes to plan quality.
5. **Keep every decision explainable.** Each match keeps a `how` value naming the rule that decided it.

---

## 5. Proposed refinements

### R1. Match on content, not verbs (P2)

**Rationale:** the step a task belongs to depends on what it is about and when it happens, not on the verb it opens with.

**Implementation**
- **Spine (`match_terms`):** a review guideline that terms describe the stage, such as "give notice", "due date" or "how much you can get". Bare action verbs ("claim", "check", "apply", "tell", "arrange") aren't allowed. Add a lint in `truth.py` that warns when a step's terms contain a verb from a stop-list.
- **`run_app.py` `match_task()`:** search the title, the task `summary` and the title of the plan step that contains the task. `trace_tasks()` already loops over plan steps and can pass that title in.
- **Optional `match_terms_exclude`:** per step, phrases that rule a task out, for disambiguation such as "for your partner".

### R2. Use the person's situation to choose between steps (P4)

**Rationale:** when a page is shared, the person's situation often settles which step applies, before any wording is considered.

**Implementation**
- **Spine:** an optional `match_when` per step, a condition over profile answers in the same form as mapping rules:
  ```json
  { "step": 3, "match_when": { "q_baby_stage": ["expecting"] } }
  ```
- **`url_index()`:** index `match_when`.
- **`match_task(task, index, answers)`:** filter the candidate steps by `match_when` before term matching. If nothing is left, fall back to the unfiltered list.
- **`_score_one()`:** pass `profile["answers"]` through `trace_tasks()`.
- This uses profile answers only, not the answer key, so matching stays independent of verdicts.

### R3. Resolve tasks that match several steps (P1, P3)

**Rationale:** a task that serves a needed step should not also count as an extra on a step that doesn't apply.

**Implementation**
- **`_score_one()`:** after looking up `truth_entry` and before building `steps`, apply `_resolve(trace, verdicts)`. If a task matches at least one `required` step, drop its matches to `not_required` steps. Matches to `optional` and `deferred` steps stay. The `how` value is suffixed `+resolved`.
- **Coverage-group policy:** an optional mapping field `coverage_groups` lists steps that one task may satisfy together, for example "check pay" and "take leave" on one page. Inside a group, one task covers every required step. Outside it, a task covers only its best-matching step. This makes the "can one task do two stages?" decision explicit for each life event.
- **Caveat:** R3 reads verdicts. It only removes matches, so it can't inflate recall. It does lift precision, so report it with and without R3.

### R4. State transitions: `deferred` and `expired` verdicts (P5)

**Rationale:** people's situations move along a timeline, and a plan that anticipates the next stage is helpful, not wrong. At the moment, a step that will apply later is `blocked` or `not_required`, so showing it is penalised as an extra or a blocked step. A step whose window has just closed looks the same as one that never applied. The same pattern comes up across life events: before and after a birth, before and after a residency threshold, before and after passing a theory test.

**Model**
- **Mapping:** a list of `transitions`, meaning answers expected to change over the course of the life event:
  ```json
  "transitions": [
    { "id": "birth", "question": "q_baby_stage", "from": ["expecting"], "to": "born" },
    { "id": "residency", "question": "<residency question>", "from": ["<under threshold>"], "to": "<over threshold>" }
  ]
  ```
  The driving entry is illustrative: use the driving model's actual question and answer IDs.
- **Blocks and rules:** an optional `until` field naming a transition:
  ```json
  { "question": "<residency question>", "answers": ["<under threshold>"], "steps": [3, 4],
    "why": "Not available until the residency condition is met", "until": "residency" }
  ```
- **`truth.py verdicts()`:** compute verdicts for the current answers as now. Then, for each transition, recompute them with the answer moved:
  - **`deferred`:** the person hasn't been through the transition. A step that is blocked or not required now, but required with the answer moved to `to`, is deferred. Record `unlocks_on`.
  - **`expired`:** the person has already been through it (their answer is the `to` value). A step that would be required with the answer moved back to `from`, but isn't now, is expired. Examples: giving notice once the baby is born, or the Sure Start grant after the claim window. This is recorded for reporting and scored as `not_required`.
  - **`blocked` (permanent):** blocked under every state. It keeps today's meaning and counts towards `presented_a_blocked_step`.
- **Keep it simple:** apply one transition at a time, with no chained or combined transitions in this version.

**Scoring (`truth.py score()`)**

| Verdict | Missing from plan | Shown in plan |
|---|---|---|
| required | miss (recall) | hit |
| deferred | neutral now; miss for journey recall | not an extra; hit for journey recall |
| optional | neutral | neutral |
| not_required / expired | — | extra (precision) |
| blocked | — | extra, and `blocked_but_present` |

- **Two recall figures:**
  - `recall_now`: required steps only. This is comparable with today's recall.
  - `recall_journey`: required and deferred steps. It rewards plans that set out what comes next.
- **Precision:** deferred steps are never extras.

**Matching:** the matcher itself doesn't change for R4. A task matched to a deferred step is tagged `anticipatory` in the trace, so reports can show how often plans look ahead.

**Worked example (driving, residency condition not yet met).** The profile has 5 required steps and 1 step blocked until residency. The plan covers 4 required steps and the blocked one.

| | Precision | Recall | Flags |
|---|---|---|---|
| Today | 4/5 = 0.80 | 4/5 = 0.80 | `blocked_but_present` |
| Under R4 | 4/4 = 1.00 | `recall_now` 4/5 = 0.80; `recall_journey` 5/6 = 0.83 | none |

**Having a Baby note:** the current truth already marks after-birth steps as required for expecting profiles, so `deferred` changes little there. The main gain is `expired` for profiles whose baby is born. Driving is expected to rely mainly on `deferred`. The same mechanism covers both.

---

## 6. Summary of data model changes

| Where | Field | Purpose | Refinement |
|---|---|---|---|
| Spine step | `match_terms` (revised guidance) | Content terms, not verbs | R1 |
| Spine step | `match_terms_exclude` | Rule out a step | R1 |
| Spine step | `match_when` | Situation filter on candidate steps | R2 |
| Mapping | `coverage_groups` | Steps one task may cover together | R3 |
| Mapping | `transitions` | Answers expected to change over time | R4 |
| Mapping block/rule | `until` | Marks a block or rule as temporary | R4 |
| Verdicts | `deferred`, `expired` (+ `unlocks_on`) | Steps that apply later, or whose window has passed | R4 |
| Score output | `recall_now`, `recall_journey`, `+resolved` and `anticipatory` tags | New reporting | R3–R4 |

All the new fields are optional. A spine or mapping without them behaves exactly as today.

---

## 7. Code changes by file

| File | Change |
|---|---|
| `run_app.py` | `url_index()`: index `match_when`, exclusions and coverage groups. `match_task()`: wider text (R1), situation filter (R2). `trace_tasks()`: pass the plan step title and answers. `_score_one()`: `_resolve()` (R3), `anticipatory` tag (R4). `_config()` and docstrings: matcher description and version. |
| `truth.py` | `verdicts()`: transitions and `deferred`/`expired` (R4). `score()`: new verdict handling and `recall_now`/`recall_journey`. Lint for verb terms (R1). `check_mapping()`: validate the new fields. |
| `prompts.py` (`map_system`, `map_tool`) | Let the one-off `map` stage propose `transitions` and `until` for human review (R4). |
| Truth and mapping files (per life event) | Revise `match_terms`. Add `match_when`, `coverage_groups`, `transitions` and `until` where relevant. |
| `tests/test_matching.py`, `tests/test_verdicts.py` (new, under `scripts/evaluation/plan-generation/`) | Focused unit tests for R1–R4 (section 8). |

---

## 8. Tests

The scope is unit tests for the behaviour this proposal adds or changes, and nothing else.

- **Small fixtures.** Most tests use a made-up spine of three or four steps that share one URL, built inside the test, so they don't depend on any one life event or on GOV.UK content.
- **Baby cases as plain data.** The three Having a Baby cases are copied in as fixtures, not loaded from data files.
- **No network, agent or judge calls.**

**`test_matching.py` (R1–R3)**

| Test | Checks |
|---|---|
| `test_single_url_step_unchanged` | A URL linked from one step still matches by `url`, and a sub-page still counts as its parent. This guards today's behaviour. |
| `test_terms_ignore_title_verb` | Two tasks on a shared URL that differ only in their opening verb ("Claim…" vs "Check…") match the same step. (R1) |
| `test_terms_read_summary_and_step_title` | A content term found only in the task summary, or only in the plan step's title, decides the step. (R1) |
| `test_match_terms_exclude` | An excluded phrase removes a step from the candidates. (R1) |
| `test_match_when_filters_candidates` | With the answer set to "born", a step limited to "expecting" is never matched. (R2) |
| `test_match_when_never_empties` | If the `match_when` filter would remove every candidate, the unfiltered list is used. (R2) |
| `test_resolve_drops_not_required_when_required_hit` | A task matching a required step and a not-required step keeps only the required one, and is tagged `+resolved`. (R3) |
| `test_resolve_keeps_optional_and_deferred` | `_resolve()` doesn't remove matches to optional or deferred steps. (R3) |
| `test_resolve_never_adds_steps` | For any input, the resolved steps are a subset of the matched steps. (R3, design principle 3) |
| `test_coverage_group` | Inside a coverage group, one task covers every required step in it. Outside it, the task covers only one step. (R3) |

**`test_verdicts.py` (R4)**

| Test | Checks |
|---|---|
| `test_no_transitions_unchanged` | A mapping without `transitions` gives exactly today's verdicts and scores. |
| `test_deferred_from_temporary_block` | A step blocked `until` a transition, for a person who hasn't been through it, is `deferred` with `unlocks_on` set. |
| `test_permanent_block_stays_blocked` | A block without `until` stays `blocked`. |
| `test_expired_after_transition` | A step required only before a transition the person has already been through is `expired`. |
| `test_score_deferred_and_expired` | Deferred steps are never extras, and count towards `recall_journey` but not `recall_now`. Expired steps score as `not_required`. Uses the worked example in R4. |

**Having a Baby regression cases (in `test_matching.py`)**

| Test | Checks |
|---|---|
| `test_paternity_pay_not_double_counted` | "Claim Statutory Paternity Pay" for a profile where step 2 isn't required covers step 7 and isn't an extra on step 2. |
| `test_maternity_pay_after_birth` | Born profile: "Claim Statutory Maternity Pay" doesn't match step 3. |
| `test_fallback_rate` | Over a small fixed sample of saved tasks, fewer than 2% of matched tasks fall back. |

---

## 9. Rollout

1. **Phase 1, matching fixes (R1, R2, R3).** Low risk, with no change to verdicts.
   - Re-score the saved Having a Baby and driving plans with `--from-raw` or from the plans file, so no new agent calls are needed.
   - Publish raw and refined scores side by side.
   - **Done when:** the `test_matching.py` tests pass, and on the full re-scored Having a Baby run the fallback rate is below 2% of matched tasks.
2. **Phase 2, time awareness (R4).**
   - Add `transitions` and `until` to the Having a Baby and driving mappings and review them.
   - Introduce `deferred` and `expired`, and report `recall_now` and `recall_journey`.
   - **Done when:** the `test_verdicts.py` tests pass, and a reviewer agrees with a sample of 20 `deferred`/`expired` verdicts for each life event.

---

## 10. Out of scope for now

These came up in the analysis but are left for later:

- **Plans flagging tasks for later:** an agent schema field such as `available_when`, which would allow stricter credit for deferred steps.
- **Ordering checks:** step dependencies (`depends_on`) and checks on the order steps appear in.
- **Tasks outside the spine:** classifying unmatched tasks (381 in this run, such as childcare support).
- **Relevance in coverage:** joining relevance verdicts, so a contradicted task can't cover a step.
- **Matcher validation:** a labelled task-to-step sample to measure how often the matcher agrees with a person. The focused tests in section 8 check known cases but don't measure accuracy.

---

## 11. Risks and open questions

- **R3 reads the answer key.** It can only remove matches, but it does favour precision. Should the main figure include it, or should it only be reported alongside?
- **How much credit for deferred steps?** Without plans flagging tasks for later, showing a deferred step counts towards `recall_journey`. Is that the right default, or should deferred steps be neutral everywhere until that flag exists?
- **How far ahead?** One transition is enough for birth and residency. Some life events may need chained states, such as theory test, then practical test, then full licence.
- **Who maintains match terms?** They change when GOV.UK content changes. Proposal: the same owner and review cadence as the mapping.
- **Rebasing comparisons.** Refined scores aren't comparable with earlier runs. Keep the raw scores in every report until the old runs are no longer referenced.

---

## Appendix A. Having a Baby figures (weighted, 38 profiles × 3 plans)

| | Precision | Recall | F1 |
|---|---|---|---|
| Reported (raw) | 0.87 | 0.60 | 0.69 |
| With R2 and R3 approximated | up to 1.00 | 0.63 | 0.76 |
| Without employment-rights steps (2, 5, 6, 10), raw | 0.96 | 0.76 | 0.84 |
| Without employment-rights steps, with R2 and R3 approximated | up to 1.00 | 0.80 | 0.88 |

Matcher diagnostics, raw run:
- 33 fallback matches
- 59 extras, 44 of them step 2 counted alongside step 7
- 14 maternity pay tasks matched only to a step that no longer applies
