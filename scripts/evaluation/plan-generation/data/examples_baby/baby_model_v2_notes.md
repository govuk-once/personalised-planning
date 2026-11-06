# Having a baby: example model, scope and weights

## What is here

| File | What it is |
|---|---|
| `baby_model_v2.json` | The elicitation model: 14 questions, 23 facts, validates clean |
| `baby_model_v2.md` | Its readable summary, from `plans.py` |
| `baby_common_path_pins.json` | The common-path scope, for `plans.py profiles --pins` |
| `baby_weights_v2.json` | Weight targets for `weights.py`; each target's `_source` field cites where it came from |

## How the model was made

1. **Subgraph.** `src/utils/build_subgraph.py` built the having-a-baby subgraph from the GOV.UK Knowledge Graph. It was then pruned to 120 pages by dropping whole browse sections (Fostering, adoption or surrogacy; Schools and education; Divorce, separation or legal issues), and each page was labelled with a `cluster`. See `docs/having-a-baby-subgraph-analysis.md`. The subgraph (`data/having_a_baby_subgraph_pruned.json`) is not committed, so you can read and sample this model, but you can't re-validate its sources without rebuilding the subgraph.
2. **Three runs.** `plans.py model --main-goal none --rationale --max-page-chars 12000`, with shuffle seeds 1, 2 and 3.
3. **Hand merge (v1).** Combined without another LLM call, using the rules and departures below.
4. **Hand edits (v2).** Fixes for combinations that made no sense. The model's `meta.revisions` records them:
   - relationship and employment are also asked after a stillbirth at 24+ weeks or a baby's death; "adopting" is hidden after a stillbirth. This resolves the first point under "Worth checking" below for those two questions. Other children and disability are still asked only if the pregnancy is ongoing or the baby is alive;
   - `q_partner_died` is asked before `q_has_partner`; `q_has_partner` is not asked of partners, or of anyone whose partner died;
   - `q_pregnancy_timing` is not asked of adopters;
   - the model uses the JSON-logic `or` operator;
   - the numeric attribute is renamed from `parent_age` to `age`, the name `run_app.py` passes to the planner.

Unpinned, the model yields 9,023 distinct profiles. Pinned to `baby_common_path_pins.json`, it yields 960.

The merge notes, as written for v1, follow.

## How this model was combined

This model combines three runs of `plans.py model --main-goal none --rationale` on the pruned having-a-baby subgraph (`data/having_a_baby_subgraph_pruned.json`), with shuffle seeds 1, 2 and 3. It was merged by hand, without another LLM call and without any scope rule, using these rules:

1. **Keep a question if an equivalent question appears in at least 2 of the 3 runs.** Each question's `merged_from` field names the run questions it combines.
2. **Wording** is the clearest version; **sources** are the union of the matched questions' sources; the **gate** (who is asked) is the one most runs used.
3. **List everything else for review** (below) instead of dropping it silently.

The model passes the same validation as a generated one (sources exist in the corpus, every question and option is reachable, every fact varies) and yields 5347 distinct profiles.

### Where the merge departs from the runs

| Question | Runs | Merged | Why |
|---|---|---|---|
| `q_nation` | s1 added "Outside the UK"; s3 combined England and Wales | England / Wales / Scotland / Northern Ireland | 2 of 3 runs kept the four nations separate |
| `q_pregnancy_outcome` | s1: alive / died or stillborn; s2: one "loss" option within a stage question; s3: ongoing / before 24 weeks / stillborn 24+ / died after birth | s3's four options | the most detailed version; the 24-week line decides between a baby loss certificate and stillbirth registration |
| `q_baby_stage` | s1: part of a child-age question; s2: part of the stage question; s3: "born yet?" | separate expecting / born question, asked if the pregnancy is ongoing or the baby alive | follows s3's structure, which both other runs can be mapped onto |
| `q_relationship_to_baby` | s1, s3: giving birth / partner / adopting / surrogacy; s2: birth vs adoption or surrogacy | the four options | 2 of 3 runs separated the birth parent from the partner |
| `q_partner_died` | s1 asked everyone; s2 asked anyone with a partner | asked of the partner, adopter or intended parent | the runs disagree (1 each), and the question only makes sense for someone other than the mother |
| `q_pregnancy_timing` | s2: under 24 / 24–26 / 26+ weeks; s3: more or less than 11 weeks before the due date | under 26 weeks / 26 weeks to 11 before due / within 11 weeks of due | combines the thresholds both runs drew from the corpus (Maternity Allowance at 26 weeks; maternity leave and the grant from 11 weeks before the due date) |
| `q_baby_age` | s1: under 9 months / 9 months–4 years / over 4; s2: under or over 26 weeks, plus an "older child" stage | under 6 months / 6–9 months / 9 months or older | combines the grant's 6-month deadline (s2) and the 9-month childcare threshold (s1) |
| `q_qualifying_benefits` | s1: if baby alive; s2: everyone except Scotland; s3: everyone, through a banded income question | asked of everyone | no two runs used the same gate; 2 of 3 asked it outside the alive-baby route |
| `q_child_disability` | s3 added "not yet known" | "Not known yet" shown only to people who are expecting | needed for people still expecting |
| `q_parent_age` | s2: "under 16?"; s3: "16 or 17?" | one question: under 16 / 16–17 / 18 or over | the same circumstance asked two ways |

### Worth checking: gates that follow the runs but may be wrong

Following the majority, employment, relationship to the baby, other children and disability are asked only when the pregnancy is ongoing or the baby is alive (2 of 3 runs gated them this way). But s3's own fact for stillbirth says the parent "may still be entitled to maternity/paternity/parental bereavement pay and leave". So people after a stillbirth or a baby's death are not asked their employment status, and the leave-and-pay route is closed to them. Widening the employment and relationship gates to everyone except "pregnancy ended before 24 weeks" would fix this, but it isn't what the runs did.

### For review: found in only one run

| Question | Run | What it would route |
|---|---|---|
| Income over £60,000 (as part of a banded income question) | s3 | High Income Child Benefit Charge. Also found in 4 of the 6 earlier `required`/`optional` runs, and recommended by the graph analysis |
| Neonatal care for 7+ days | s1 | Neonatal Care Pay and Leave. Also in 2 of the 3 earlier `required` runs |
| Born in the UK or abroad | s1 | Registering a birth abroad |
| Parents married or in a civil partnership | s1 | Parental responsibility for the father or second parent |
| Working, or on qualifying leave, for childcare help | s1 | Free Childcare for Working Parents, Tax-Free Childcare |
| Multiple birth | s2 | Sure Start Maternity Grant exception and amount |
| About to employ a nanny or carer | s3 | Employer responsibilities |
| "Outside the UK" as a nation option | s1 | Not living in the UK at all |

### Numeric attributes

Only parent age (numeric attribute `age`, the name `run_app.py` passes to the planner) is kept, bounded by the `q_parent_age` answer. Pregnancy weeks and baby age are covered by the `q_pregnancy_timing` and `q_baby_age` bands instead. Income and weekly earnings were not kept: s1 and s3 bounded income with editorial floors only, and only s3 used weekly earnings (the £129 a week earnings threshold for statutory pay).
