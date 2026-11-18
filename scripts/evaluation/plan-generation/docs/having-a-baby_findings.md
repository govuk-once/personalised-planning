# Findings from the end-to-end evaluation pipeline run for having a baby
Date: 18th Nov 2026
Author: Jyl Djumalieva

This document describes findings from the first end-to-end evaluation pipeline run. Life event in scope is Having a baby. Findings cover results for both auto-evaluation and manual evaluation work streams.

## Profiles that were used
GOV.UK sub-graph on becoming a parent was used to generate a model from three runs without `main_goal` requirement (see `scripts/evaluation/plan-generation/data/examples_baby/baby_model_v2_notes.md`).
A decision was made to pin the scope of synthetic profile generation to a subset of model journeys that represent the most common paths. This resulted in 960 profiles, these were also weighted using `scripts/evaluation/plan-generation/data/examples_baby/baby_weights_v2.json`. These common path profiles account for roughly 75% of underlying population.
Out of 960 profiles, 3 plans were generated for each of the 38 heaviest profiles using the deployed planning agent. These 38 profiles account for about 54% of common path journeys (~40% of the overall population).


## Headline figures
Overall, the plans contain appropriate and relevant steps and their facts mostly agree. At the same time, some steps are consistently left out.

| Metric | Score (weighted) |
|---|---|
| Step precision / recall / F1 | 0.87 / 0.60 / 0.69 (2 plans perfect, 112 missed at least one required step) |
| Relevance | 0.976 (26 tasks contradicted, 1 irrelevant, out of 912) |
| Fact consistency | 0.98 |
| Service stability (overlap of services between plans) | 0.73 |
| Structure consistency | 0.03 |

## Key insights
1. Lower recall is partially explained by mismatch between content in the service-graph and ground truth plan. Service graph does not contain information on steps related to employer rights during pregnancy: taking time off for antenatal appointments, starting maternity leave and return to work. If we omit employment right steps, not covered in the service-graph, recall lifts from 0.60 to 0.76 (F1 lifts from 0.69 to 0.80).
2. Precision and recall measures can also be improved by better matching of service URLs that are shared between plan steps. A refinement to matching methodology alone will result in increase in precision from 0.87 to 1 and recall from 0.6 to 0.63 (F1 lifts from 0.69 to 0.76).
3. Plans often include childcare services like tax-free childcare and 30h free childcare allowance, which are not listed in the ground truth.
4. Steps are not made the same. Some steps are mandatory, whereas others are advisory. For example taking time off for antenatal appointments is not something a user must do. Current calculations of precision and recall only take into account if a step is optional, but not gradations of step importance.
5. Overall tasks across plans are relevant to user circumstances. Exceptions are contradicted tasks (26 out of 912) that have conditions that the user profile doesn't meet (e.g. baby's age vs eligibility for the service).
6. Facts in plans are consistent; the core services are stable, but agent organises them differently each time. Difference in services listed stems from more optional services, such as childcare, Healthy Start and NI credits.

## Implications and recommendations

### Improving plan quality
- Revisit steps that are consistently missing in the plans and add to service-graph if truly required
- Revisit services that most often are unmatched in plans and add to ground truth if these are immediately relevant to common user profiles.
- Develop more nuanced categorisation of step/task importance, based on consequences for user.

### Improving plan relevance
- Introduce eligibility checks against user profile to minimise contradicted tasks.

### Refining metrics
- Improve matching of steps and tasks between agent generated plans and ground truth.
- Change definition of structure consistency to look at overall step composition regardless of order.
- Have the relevance judge check whether an action is still timely, not just whether the person is eligible
