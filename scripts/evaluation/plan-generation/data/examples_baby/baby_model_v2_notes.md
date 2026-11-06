# Having a baby: example model, scope and weights

## What is here

| File | What it is |
|---|---|
| `baby_model_v2.json` | The elicitation model: 14 questions, 23 facts, validates clean |
| `baby_model_v2.md` | Its readable summary, from `plans.py` |
| `baby_common_path_pins.json` | The common-path scope, for `plans.py profiles --pins` |
| `baby_weights_v2.json` | Weight targets for `weights.py`; each target's `_source` field cites where it came from |

The model yields 9,023 distinct profiles unpinned, and 960 when pinned to `baby_common_path_pins.json`.

## How the model was made

The model was built in four steps. Steps 3 and 4 were done by hand, so the model is not the direct output of a `plans.py model` run.

1. **Subgraph.** `src/utils/build_subgraph.py` built the having-a-baby subgraph from the GOV.UK Knowledge Graph. Three whole browse sections were then dropped, leaving 120 pages:
   - Fostering, adoption or surrogacy
   - Schools and education
   - Divorce, separation or legal issues

   Each page was labelled with a `cluster` (see "How the subgraph was pruned and clustered" below). The pruned subgraph (`data/having_a_baby_subgraph_pruned.json`) is not committed. You can read and sample this model without it, but re-validating its sources means rebuilding the subgraph.
2. **Three runs.** `plans.py model --main-goal none --rationale --max-page-chars 12000` was run three times, with shuffle seeds 1, 2 and 3 (referred to below as s1, s2 and s3).
3. **Merge.** The three runs were combined by hand, without another LLM call and without any scope rule (see "Merge" below). The merged model validated clean and yielded 5,347 distinct profiles.
4. **Manual review.** Answer combinations that made no sense were fixed, giving the model here, which yields 9,023 distinct profiles (see "Manual review" below). The model's `meta.revisions` lists the same edits.

## How the subgraph was pruned and clustered

A one-off script, not in the repo, did the pruning and clustering. A rebuild can follow the same rules, but it won't run the same code.

**Browse sections.** The subgraph does not record which browse section each page belongs to. Section membership was therefore taken from the live GOV.UK Search API (`filter_mainstream_browse_pages=childcare-parenting/<section>`, queried 2026-11-03). Three sections were excluded:
- `fostering-adoption-surrogacy`
- `schools-education`
- `divorce-separation-legal`

**Pruning rule.**
1. Drop a seed page only if **every** section it is tagged to is excluded. Pages tagged to more than one section stay if any of their sections is kept: 25 pages are tagged to more than one.
2. Drop any 1-hop neighbour that is no longer linked from a kept seed.
3. Also drop excluded-section pages that come back in as neighbours of kept seeds.

**Result.**

| Step | Pages | Links |
|---|---|---|
| Original subgraph | 184 | 459 |
| Excluded-section pages removed | −42 | |
| Neighbours left unlinked | −22 | |
| **Pruned subgraph** | **120** | **320** |

The original count is of unique content IDs. Welsh translations share an ID with their English page.

**Tagging anomaly.** Three birth-registration pages are tagged only to Divorce/legal, so the rule removed them:
- `/adding-fathers-name-birth-certificate`
- `/adding-second-female-parents-name-birth-certificate`
- `/correct-birth-registration`

**Clusters.** Louvain community detection (`networkx`) labelled each page with a `cluster`:
- links treated as two-way;
- resolution 1.0;
- the best modularity over seeds 0–19 was 0.48;
- across 50 runs, the members of each main cluster were grouped together 88–100% of the time.

There are five main clusters (`benefits_core`, `childcare`, `work_leave_pay`, `child_benefit_admin`, `birth_registration`) plus eight small ones. `compare_models.py` reads these labels.

## Merge

### Rules

1. **Keep a question if an equivalent question appears in at least 2 of the 3 runs.** Each question's `merged_from` field names the run questions it combines.
2. **Wording, sources and gate.**
   - Wording is the clearest version.
   - Sources are the union of the matched questions' sources.
   - The gate (who is asked) is the one most runs used.
3. **List everything else for review** (below) instead of dropping it silently.

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

### Found in only one run, so not kept

These are candidates for a later version.

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

## Manual review

Following the majority, the merge asked four questions only when the pregnancy was ongoing or the baby was alive (2 of 3 runs gated them this way):
- employment
- relationship to the baby
- other children
- disability

But s3's own fact for stillbirth says the parent "may still be entitled to maternity/paternity/parental bereavement pay and leave". So people after a stillbirth or a baby's death had no route to leave and pay. The review fixed this, and some other illogical combinations:

- **Relationship and employment** are now asked after a stillbirth at 24+ weeks or a baby's death as well, but not after a pregnancy ended before 24 weeks. "Adopting" is hidden after a stillbirth.
- **Partner questions.** `q_partner_died` is asked before `q_has_partner`. `q_has_partner` is not asked of partners, since being a partner already implies one (`fact_has_partner` covers it), or of anyone whose partner died.
- **`q_pregnancy_timing`** is not asked of adopters.
- **JSON-logic `or`.** The model uses the `or` operator, which these fixes needed.
- **Numeric attribute.** `parent_age` was renamed to `age`, the name `run_app.py` passes to the planner.

**Still open.** Other children and disability are asked only if the pregnancy is ongoing or the baby is alive.

## Numeric attributes

Parent age (`age`) is the only numeric attribute kept, and the `q_parent_age` answer bounds it. Pregnancy weeks and baby age are covered by the `q_pregnancy_timing` and `q_baby_age` bands instead.

Income and weekly earnings were not kept:
- s1 and s3 bounded income with editorial floors only.
- Only s3 used weekly earnings (the £129 a week earnings threshold for statutory pay).
