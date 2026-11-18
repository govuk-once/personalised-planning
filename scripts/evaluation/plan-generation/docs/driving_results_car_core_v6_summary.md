# Driving (car core, v6.2): results summary

Evaluation of the planner against the `/learn-to-drive-a-car` step-by-step guide, using plans generated on 2026-11-17. The run includes rarer cases: an expired theory pass, failing the eyesight standard, and two GB residency rules.

## Summary

In the common cases the planner gets everything it can reach right, but covers only about a third of the guide. For the four profiles with nothing blocking them (96% of the weight), the 12 plans score:

- **precision:** 1.0
- **full-guide recall:** 0.34, weighted 0.32 (graph gap removed: 1.0)
- **full-guide F1:** 0.50, weighted 0.48 (graph gap removed: 1.0)

The planner also correctly tells someone with an expired theory pass to take the test again.

**How step 1 is scored.** The answer key treats step 1, "Check you're allowed to drive", as already done for anyone who told the questionnaire they meet the eyesight standard. The questionnaire has effectively carried out that check, so the step isn't required in their plan. It stays required for anyone who fails the eyesight standard, because for them the eyesight rules are exactly what they need.

Full-guide recall is the primary measure. It counts every step in the guide that applies to the person, including step 1 and the optional steps 3, 4 and 7.

The bracketed "graph gap removed" figures use the answer key instead, where step 1 is treated as done for people who meet the eyesight standard and steps 3, 4 and 7 are optional. In this run, that comes to the same thing as counting only the steps whose pages are in the service graph. The difference between the two is the graph gap: all the guidance pages for steps 1, 3, 4 and 7 are missing from the graph, so the planner can't cite them.

The rarer cases this run was built to test are where it fails. In all 21 plans for the seven profiles who fail the eyesight standard or don't meet a residency rule, the planner still lists the steps those people can't take. Typically these are booking the driving test, and sometimes the theory test or a provisional licence. Every one of those plans mentions the condition, but only as a caveat on a task marked "Not started". The planner's step status can't say a step isn't available yet.

For the eyesight cases the advice is wrong by GOV.UK's rules.

The two residency rules are where the planner is most confused. GOV.UK has two separate conditions:

- Permission to live in GB for 185 days is needed to apply for a provisional licence.
- Having lived in England, Scotland or Wales for 185 days in the last 12 months is needed to take the theory and driving tests.

The planner handles them like this:

| Profile | Situation | What the plans do | Verdict |
|---|---|---|---|
| P012 | No permission to live in GB, and so hasn't lived here 185 days | All 3 plans flag the provisional licence as blocked, but describe both conditions as provisional licence rules. They still list the theory and driving tests with no residency warning, and one plan cites a page that doesn't exist. | Partly right |
| P005 | Has permission but hasn't lived here 185 days | All 3 plans apply the 185-days rule to the provisional licence, telling them they can't apply yet. None mentions it on the theory or driving test. | Backwards: they can apply, but can't take either test |
| P003, P008 | Already hold a provisional licence, and haven't lived here 185 days | Attach the rule to the tests, but only as a soft caveat ("may affect", "check before booking"), and not in every plan | Closest to right |

Because these profiles carry under 4% of the weight, the weighted F1 (0.96) hides the problem; the unweighted F1 is 0.43. The relevance judge mostly accepts the blocked steps, so the answer key's blocked-step count is the only measure that catches them. Relevance and consistency are also pulled down by things that aren't errors in the advice:

- Steps the planner marks Done are judged contradicted.
- Some Done tasks are given a £0 cost and others the full fee.
- Vehicle tax is added to most plans for learners with no car.

**Out-of-guide tasks are almost all judged irrelevant.** 22 tasks in 19 of the 33 plans cite a service that isn't in the guide:
- vehicle tax: in all 19 of those plans
- a SORN and Clean Air Zone charges: in one P018 plan
- a mistyped provisional licence URL: in one P012 plan

Across the judge's 110 verdicts on these tasks (5 repeats each):
- **88% `irrelevant`:** "nothing indicates they own a car"
- **7% `relevant`:** all vehicle tax, judged a plausible later need
- **5% `contradicted`:** the mistyped licence task, for someone who can't apply yet

By comparison, 70% of the verdicts on tasks inside the guide are `relevant`; most of the rest are Done tasks and blocked steps. So the planner rarely adds anything useful beyond the guide, and what it does add is almost always vehicle tax for someone who hasn't said they have a car.

**Why these tasks appear.** The service graph's "Learning to Drive" journey includes services for owning a car, such as vehicle tax, SORN and Clean Air Zone charges, and lists them alongside the first steps of learning. It also flags them as worth mentioning even if the person hasn't asked. The questionnaire never asks whether the person has a car, so the planner can't tell whether they apply. It includes vehicle tax in some plans and not others, which also explains much of the variation between plans for the same person.

Seven of the rarest profiles fell below the minimum weight and have no plans yet.

### If blocked steps can count when the dependency is stated

This is an estimate, not a pipeline result. It re-scores plan quality by hand to test a less strict reading of the answer key.

**How blocked steps are scored:**
- **Shown, with the dependency clearly stated:** treated as required for that plan, so it counts as a hit.
- **Shown, without it:** stays blocked.
- **Not shown:** still neutral.

**What counts as clearly stated (strict definition):** the step's own text says the person doesn't currently meet the condition and must resolve it first. For example: "this needs to be resolved before you apply", "It cannot be booked until the eyesight standard is met", or "booking may not be possible until it is". These don't count:
- hedged wording such as "may affect your ability to book" or "check this before booking"
- a generic requirements line
- a mention only in the plan summary

**How many qualify:** only 8 of the 42 places where a blocked step appears.

| Where the dependency is stated | Steps |
|---|---|
| P012, all 3 plans | Step 2 |
| P002, 2 plans | Step 2 |
| P004, P008 and P017, 1 plan each | Step 6 |
| P003, P005 | Never |
| Any profile | Never on step 5 |

**What counts under the lenient definition:** the step's own text says the condition applies to it and the person doesn't currently meet it, even if the wording is hedged. For example: "this is not currently the case, which may affect your ability to book it", or "You've indicated you don't currently meet the eyesight standard required at the test". As before, these don't count:
- a generic requirements line
- a mention only in the plan summary

**How many qualify:** 18 of the 42 places where a blocked step appears. That includes the 8 that pass the strict definition.

| Where the dependency is stated | Steps |
|---|---|
| P002, P012, all 3 plans | Step 2 |
| P008, P017, all 3 plans | Step 6 |
| P003, plan 1 | Steps 5 and 6 |
| P003, plans 2 and 3 | Step 5 |
| P004, plans 2 and 3 | Step 6 |
| P005 | Never |

| Metric | As scored | Strict estimate | Lenient estimate |
|---|---|---|---|
| Blocked profiles: precision / recall / F1 | 0.07 / 0.19 / 0.10 | 0.25 / 0.45 / 0.30 | 0.57 / 0.79 / 0.61 |
| Blocked profiles, weighted: precision / recall / F1 | 0.05 / 0.13 / 0.07 | 0.19 / 0.31 / 0.22 | 0.65 / 0.87 / 0.70 |
| Blocked-profile plans still presenting a blocked step with no stated dependency | 21 of 21 | 19 of 21 | 14 of 21 |
| All profiles: precision / recall / F1 | 0.41 / 0.48 / 0.43 | 0.52 / 0.65 / 0.55 | 0.73 / 0.86 / 0.75 |
| All profiles, weighted: precision / recall / F1 | 0.96 / 0.97 / 0.96 | 0.97 / 0.97 / 0.97 | 0.99 / 0.99 / 0.99 |
| Perfect plans (of 33) | 12 | 14 | 17 |

Under the lenient definition, P008 and P017 have no blocked step left without a stated dependency, but the others still do:

- **P002:** the eyesight condition is never carried forward to the theory or driving test.
- **P004:** the eyesight condition is never carried forward to the theory test.
- **P003:** only plan 1 mentions residency on the driving test.
- **P005:** the warning is on the wrong step.
- **P012:** no warning on either test.

Even on the strict reading, the blocked cases stay poor. The planner rarely carries the condition forward to the later steps it blocks, and 24 of the 42 blocked steps have no personalised mention at all. The classifications are one reviewer's reading of the plan text.

## Run

| | |
|---|---|
| Model | `data/models/driving_model_refactor_v6_2.json`, including 4 questions for rarer cases (below) |
| Mapping | `data/mappings/driving_mapping_v6_2.json`: 5 rules, 3 blocks, steps 3, 4 and 7 marked optional |
| Profiles | `data/profiles/driving_profiles_v6_2_car_core_w.json`: 18 profiles, pinned to car, no medical condition, no accessibility needs. Weighted with `data/weights/driving_weights_v6_2_car.json` (effective sample size 2.8). |
| Plans | `data/generated_plans/driving_plans_v6_2_car_core.json`: G = 3, `--min-weight 0.001`. 11 profiles generated (33 plans, 0 failures); 7 skipped as below the minimum weight (0.2% of the weight). |
| Answer key | `data/ground_truth/driving_truth_v6_2_car_core.json`: 8 distinct answer keys |
| Plan quality | `data/results/driving_quality_v6_2_car_core.json` (`run_app.py --from-plans`) |
| Relevance and consistency | `data/results/driving_results_v6_2_car_core.json` (`metrics.harness score`, N = 5, judge `claude-sonnet-5-5`) |

### Questions and rules for the rarer cases

**Questions:**

| Question | Answer that matters | Answer-key effect |
|---|---|---|
| `q_car_theory_pass_valid` | `expired` | Steps 4 and 5 stay required |
| `q_car_meets_eyesight_standard` | `no` | Steps 2, 3, 5, 6 and 7 blocked; step 4 not required; step 1 stays required |
| `q_car_meets_eyesight_standard` | `yes` | Step 1 not required (see below) |
| `q_car_permission_to_live_in_gb` (asked only if no provisional licence) | `no` | Steps 2, 3, 5, 6 and 7 blocked |
| `q_car_lived_in_gb_185_days` | `no` | Steps 5 and 6 blocked |

The rules come from GOV.UK pages in the corpus:

- `/driving-eyesight-rules`: "If you cannot [read the number plate], you'll fail your driving test… your licence will be revoked."
- `/apply-first-provisional-driving-licence`: to apply you must "be able to read a number plate from 20 metres away" and "have been given permission to live in Great Britain… for at least 185 days".
- `/book-theory-test` and `/book-driving-test`: "You must have lived in England, Wales or Scotland for at least 185 days in the last 12 months before the day you take your theory or driving test."
- `/theory-test`: a pass certificate lasts 2 years.

**Optional steps:** steps 3 (lessons and practice), 4 (theory revision) and 7 (when you pass) are `optional`. They don't count towards recall, and showing them is neutral. A block or a dropping rule takes precedence.

**Step 1 rule:** `{"step": 1, "fact": "f_car_fails_eyesight_standard", "drop_when": false}`.
- **Meets the eyesight standard:** step 1 is `not_required`, because the questionnaire has already done the check.
- **Fails it:** step 1 stays required.

A plan that shows step 1 to someone who meets the standard would lose precision. None of the 33 plans does.

**Scorer:** plan steps the planner marks `status: "Done"` are not scored.

**Weights:** the shares for the four questions are labelled assumptions (A5 to A8 in the weights file) and still need sources:

- expired theory pass: 10% of those who passed
- fails the eyesight standard: 1%
- no permission to live in GB: 2%
- not lived in GB for 185 days: 3%

### Profiles scored

The 11 profiles that were generated fall into two groups:

| Group | Profiles | Weight | Answer key |
|---|---|---|---|
| **Unblocked** | P011 (no licence yet); P014 (provisional licence); P015 (provisional licence, expired theory pass); P018 (provisional licence, valid theory pass) | 96.0% | Only steps 2, 5 and 6 can be required |
| **Blocked on a step the graph can reach** | P002, P004, P017 (fail eyesight); P003, P005, P008 (not lived in GB for 185 days); P012 (no permission to live in GB and not lived 185 days) | 3.8% | Steps 2, 5 or 6 blocked. Only step 1 is required for the eyesight-fail profiles, only step 2 for P005, and nothing for P003, P008 and P012. |

**Not generated** (below `--min-weight` 0.001): P001, P006, P007, P009, P010, P013 and P016. These are:

- 3 of the 4 expired-theory profiles
- 5 of the 9 eyesight-fail profiles
- the only profile combining no permission to live in GB with failing eyesight

Some profiles fall into more than one group.

## Headline scores

| Metric | Mean | Weighted |
|---|---|---|
| Plan quality: precision | 0.41 | 0.96 |
| Plan quality: recall | 0.48 | 0.97 |
| Plan quality: F1 | 0.43 | 0.96 |
| Perfect plans | 12 / 33 | |
| Plans presenting a blocked step | 21 / 33 | |
| Relevance | 0.61 | 0.55 |
| Service stability | 0.78 | 0.77 |
| Fact consistency | 0.77 | 0.77 |
| Structure consistency | 0.07 | 0.08 |

Plan quality by group:

| Group | Plans | Precision | Recall | F1 | Presented a blocked step |
|---|---|---|---|---|---|
| Unblocked | 12 | 1.00 | 1.00 | 1.00 | 0 |
| Blocked | 21 | 0.07 | 0.19 | 0.10 | 21 |

## Findings

### 1. Without blocks, the planner gets every required step

All 12 unblocked plans are perfect: precision, recall and F1 are all 1.0. Each covers exactly the required steps:
- P011 (no licence yet): steps 2, 5 and 6
- P014, P015: steps 5 and 6
- P018 (valid theory pass): step 6

Each shows nothing the person doesn't need.

**Against the whole guide, recall is lower.** Counting every step that applies to them, including step 1 and the optional steps 3, 4 and 7, recall would be:

| Profile | Full-guide recall |
|---|---|
| P011 | 0.43 |
| P014, P015 | 0.33 |
| P018 | 0.25 |
| Mean (weighted) | 0.34 (0.32) |

None of the pages for steps 1, 3, 4 and 7 are in `mcp-servers/service-graph/src/graph-data.ts`. For step 1 those are `/vehicles-can-drive`, `/legal-obligations-drivers-riders` and `/driving-eyesight-rules`. Only 1 of the 33 plans covered step 1: P017 plan 2 cited `/driving-eyesight-rules`, a page not in the local graph data.

**Theory expiry is handled correctly.** All 3 plans for P015 mention that the pass has expired and include the theory test again (step 5).

### 2. Blocked steps are always presented, though with a caveat

All 21 plans for blocked profiles present at least one blocked step:

- step 6 in 21 plans
- step 5 in 15 plans
- step 2 in 6 plans

In every one of these plans, the planner does mention the blocking condition somewhere, in the plan summary or a task callout. But it still lists the blocked steps as tasks to do, with status "Not started". The planner's step status (`StepProgress` in `agent/app/structured_outputs.py`) can only be "Not started", "In progress" or "Done". It has no way to mark a step as not yet available.

How serious this is depends on the condition:

**Fails the eyesight standard (P002, P004, P017).** The plans are wrong by GOV.UK's rules.
- P002's plans still say to apply for a provisional licence, with the callout: "You currently do not meet the eyesight standard required to hold a licence — this needs to be resolved before the licence can be used to drive."
- GOV.UK says meeting the eyesight standard is a condition of applying.

**Not lived in GB for 185 days, already holding a provisional licence (P003, P008).** The plans attach the rule to the right tests, but as a soft caveat and still listed as "Not started". For example, P003 plan 1: "This test normally requires you to have lived in Great Britain for at least 185 days in the last 12 months… which may affect your ability…".
- P003 plan 3 and P008 plan 2 mention it only in the plan summary, not on the test itself.
- This is the closest to acceptable, because the block is temporary.
- The scorer only sees which steps appear, not the caveats.

**Permission to live in GB, but not lived here 185 days (P005).** All 3 plans apply the rule to the wrong step:
- They attach the 185-days rule to the provisional licence, which P005 is allowed to apply for. Plan 1 says: "You need to have been normally resident in Great Britain for at least 185 days in the last 12 months to apply."
- They give no residency warning on the theory or driving test, which are the steps it does block.

**No permission to live in GB (P012).** All 3 plans flag the provisional licence as not yet possible, which is correct. But they:
- Describe both conditions as provisional licence rules. Plan 1: "You've told us you haven't lived in Great Britain for 185 days in the last 12 months and don't currently have permission to live in Great Britain — both are conditions of this licence."
- Still list the theory and driving tests, with no residency warning on either.
- In plan 1, cite a URL that doesn't exist (`/apply-first-provisional-licence`).

### 3. The weighted scores hide the blocked-step failures

The unblocked profiles carry 96% of the weight, and P014 alone carries 50%. So the weighted F1 is 0.96, against an unweighted mean of 0.43. The blocked cases this run was designed to test make up 3.8% of the weight. Read the per-group table, not the weighted figures, for these cases.

### 4. The relevance judge mostly accepts blocked steps

Across the 220 judged tasks for blocked steps (repeats included, Done tasks excluded), the judge marked 184 `relevant` (84%) and 36 `contradicted` (16%).

| Profile | Condition | Verdicts on blocked-step tasks |
|---|---|---|
| P003, P004, P017 | lived 185 days / eyesight | All relevant |
| P002 | eyesight | 42 relevant, 3 contradicted (all 3 in one repeat) |
| P005, P008 | lived 185 days | Almost all relevant |
| P012 | no permission | 30 of 50 contradicted |

So relevance is not a check on blocked steps. The answer key's `presented_a_blocked_step` is the measure to use.

Two other things lower relevance:

- **Done tasks are judged `contradicted`.** 20 of the 33 plans have a Done step. Leaving those tasks out raises relevance from 0.61 to 0.76 (weighted 0.55 to 0.76). The effect is largest for:

  | Profile | Relevance as scored | Without Done tasks |
  |---|---|---|
  | P008 | 0.31 | 0.70 |
  | P017 | 0.39 | 0.86 |
  | P018 | 0.33 | 0.62 |

- **Vehicle tax is judged `irrelevant`.** It appears in 19 of the 33 plans. P018 plan 1 also adds a SORN and Clean Air Zone charges.

### 5. Consistency is lowered mostly by how Done steps are written

- **Fact consistency is 0.77.**
  - 51 of the 90 contradictions are for the provisional licence, and almost all are cost: £34 in one plan, £0 in another.
  - The planner sets a cost of £0 on 12 of the 20 Done provisional licence tasks, and on 3 of the 9 Done theory test tasks, but leaves £34 or £23 on the rest.
- **Structure consistency is 0.07.** Almost no pair of plans has the same structure. Plans differ in three ways:
  - whether they include a vehicle tax step (19 of 33 plans do)
  - whether they include Done steps (20 of 33 do)
  - how the summary is worded
- **Service stability is 0.78.**

## Caveats

- **The rare cases are thin.** 11 profiles and 33 plans were scored, and 7 of the rarest profiles have no plans. Each blocked condition rests on 1 to 3 profiles.
- **The new weights are assumptions, not sourced figures.** The effective sample size is 2.8.
- **The scorer can't see caveats.** It sees which steps are present, not how they're worded. A blocked step shown with a clear warning is scored the same as one shown without.
- **The eyesight-fail profiles can never score above 0.** All 9 have only step 1 required, and step 1's pages aren't in the graph. So P002, P004 and P017 score F1 0 even if the planner avoided every blocked step. P017 plan 2 is the exception: it cited `/driving-eyesight-rules` anyway.
- **Some profiles have nothing required.** For P003, P006, P008 and P012, every step is optional, blocked or not required. A plan for them scores 1.0 only if it shows no blocked or not-required step, so their score measures only whether blocked steps were avoided.
- **The score measures the steps that matter for each person, not the whole guide.** With step 1 handled by the questionnaire and steps 3, 4 and 7 optional, the gap in the service graph no longer shows in recall. Report full-guide recall (0.34 for the unblocked profiles) alongside it.

## Suggested next steps

1. **Give the planner a way to hold back steps.** Either add a status such as "Not available yet" to `StepProgress`, or tell the planner to leave out steps the person can't take. Then decide whether the scorer should treat that status like Done.
2. **Generate the 7 skipped profiles.** Re-run `generate` with `--min-weight 0`, then both scorers, so every rare case has plans. This is 54 agent calls for the full set.
3. **Add the step 1 pages to the service graph,** starting with `/driving-eyesight-rules`. Until then, recall and F1 for the eyesight-fail profiles mean little.
4. **Make relevance match the answer key:**
   - leave Done tasks out of relevance, as plan quality now does
   - consider telling the judge that some conditions block a step outright
5. **Fix how Done steps are written:** either always give a Done task a cost of £0, or never. Or leave Done tasks out of fact and structure consistency.
6. **Review why the planner adds vehicle tax,** and in one plan a SORN and Clean Air Zones, for learners with no stated vehicle.
7. **Source the four new weight shares** (A5 to A8 in `data/weights/driving_weights_v6_2_car.json`), then re-weight.

## Widening the evaluation further

This run covers the expired theory pass, the eyesight standard and both residency rules. Other cases still to add:

**Profiles that need no mapping change.** Medical condition = yes, an accessibility need, age 17 exactly or over 70, and different situation text. These get existing answer keys, so they mainly test relevance and consistency. Report them separately from the weighted figures.

**Still to do in the model and mapping:**

| Case | Change | Notes |
|---|---|---|
| Northern Ireland | Leave NI out of scope | Judge only; checks the planner doesn't send someone in NI down the GB route (review Issue 7) |
| Under 17, and PIP higher-rate mobility | Step 2 required; steps 3, 5 and 6 blocked under 17 (under 16 with PIP) | Needs an age-band question or a change to `truth.py` |
| Progress (already taking lessons, test booked) | — | Low value, and conflicts with Done handling |
| Lost or expired provisional licence | — | The spine has no renewal service |

**Extra actions, not steps.** Medical conditions and accessibility needs change what the person must do, not which steps apply. Issues 2 and 3 of `docs/driving_truth_v6_review.md` propose a per-profile `must_mention` list in the answer key, scored separately.

The v6 weights put 96% of the weight on accessibility needs. That's because the weights don't target that question, so it keeps the sampled spread; among real learners the share is far lower.
