# Having a baby: mapping review

## Files

| File | What it is |
|---|---|
| `baby_v2_mapping_generated.json` | The mapping `truth.py map` produced, unedited |
| `baby_v2_mapping.json` | The reviewed mapping used by `truth.py build`. Its `revisions` list logs the edits, and each added rule carries `added_by` |

## Inputs

- **Model:** `data/examples_baby/baby_model_v2.json`
- **Spine:** `data/having_a_baby_sbs_2026-11-02.json` (repo root), base path `/having-a-baby`, 10 steps
- **Mapping prompt:** the no-main-goal version, including two additions made before this run:
  - a step can have several rules;
  - later steps still apply to people at an earlier stage.

## Generated mapping

The generated mapping validated clean, with 13 rules and no blocks.

Its scope is:
- the pregnancy is ongoing or the baby is alive;
- the person is the birth parent or partner;
- not Northern Ireland.

The scope is kept unchanged.

## Edits (manual review, 2026-11-06)

| Step | Change | Reason |
|---|---|---|
| 9 Claim money and support | Removed 3 rules: qualifying benefits = yes, first child, not Scotland | They come from the Sure Start Maternity Grant item only. Step 9 also has Child Benefit and the benefits calculator, which apply to everyone |
| 2, 4, 6, 7, 10 | Added: keep only if `q_employment_status` is `employee` or `worker` | The generated mapping ignored employment, so self-employed and non-working people were told to tell an employer, take leave and return to work |
| 6 Start your maternity leave | Added: drop once the baby is born (`fact_baby_born`, `drop_when: true`) | Starting maternity leave is in the past by then |
| 3 Give notice | No rule added | It includes the Maternity Allowance form for birth parents without SMP, so it applies to every employment status |

The mapping now has 16 rules.

## Known limits

- **Rules apply to whole steps.** Many steps split by actor or condition within the step, for example Sure Start Maternity Grant only with a qualifying benefit. The mapping can only include or exclude whole steps.
- **Step 3 should mean "any birth parent, but a partner only if employed".** That needs either of two questions to decide it, which rules can't express. So partners who are not working or are self-employed still get step 3.
- **Workers and leave.** Strictly, Statutory Maternity and Paternity Leave are for employees only; workers can get the pay but not the leave. Steps 6 and 7 keep workers in. Narrow them to `employee` if the answer key should follow the leave rules exactly.

## Result on the 960 common-path profiles

- Every profile is in scope.
- Each gets between 3 and 10 required steps.
- Self-employed and non-working people now get steps 1, 3, 5, 8 and 9, depending on stage.
