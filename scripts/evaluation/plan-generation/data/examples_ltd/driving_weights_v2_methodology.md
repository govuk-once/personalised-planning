# Learner-driver weighting model (v2)

## Recommended scope

This weighting model targets **Great Britain users seeking help with the GOV.UK car-learning journey**, not all people using driving-related government services and not the population of all UK licence holders.

Accordingly:

- `q_main_goal.learn_to_drive = 1.0`
- `q_vehicle_type.car = 1.0`
- all alternative goals and vehicle types receive zero weight

Northern Ireland has a separate licensing and testing system, and the source test statistics cover Great Britain.

## Point estimates

| Question | Answer weights | Basis |
|---|---:|---|
| `q_have_provisional` | no 0.147; yes 0.853 | Journey-entry proxy using 788,021 first-provisional applications (2014), plus annualised Jul-Sep 2024 volumes of 2,768,000 car theory tests and 1,796,000 car practical tests. |
| `q_has_theory_cert` | no 0.664; yes 0.336 | The practical-test stage as a share of the same three-stage proxy volume. |
| `q_accessibility_need` | no 0.88; yes 0.12 | Assumption anchored to Census 2021 disability prevalence for younger age groups and the range of theory-test support offered. |
| `q_pip_mobility` | no 0.985; yes 0.015 | Conservative assumption; public PIP data do not provide the required learner-driver cross-tabulation. |

## Calculation

Using:

- first provisional applications: 788,021
- annualised theory-test volume: 692,000 x 4 = 2,768,000
- annualised practical-test volume: 449,000 x 4 = 1,796,000
- proxy total: 5,352,021

The stage targets are:

- no provisional = 788,021 / 5,352,021 = 0.147
- has provisional = 1 - 0.147 = 0.853
- has theory certificate = 1,796,000 / 5,352,021 = 0.336

This is deliberately a **page-user intent proxy**, not an estimate of unique learners. Test volumes include repeat attempts; first-provisional data are older than the test data; and GOV.UK page analytics are not public.

## Structural diagnostics on `driving_profiles_v5.json`

The 90-profile universe contains only 16 in-scope car-learning profiles. Applying the marginal targets as independent factors gives:

- weight sum: 1.000
- Kish effective sample size: 3.15 profiles
- largest single profile weight: 49.1%
- profiles aged 24 or under: 22.3% of weighted mass
- profiles aged 70 or over: 3.4% of weighted mass
- logically inconsistent `no provisional` + `has theory certificate`: 4.9% of weighted mass

These are properties of the **profile design**, not evidence about learners. The most common categorical combination happens to be attached to a 45-year-old persona, so question-level raking inadvertently makes that one persona dominate. This means the weights are suitable for a provisional comparison of plan quality across routing facts, but not for claiming population-representative demographic performance.

## Recommended follow-up before using the metric externally

1. Regenerate the in-scope car profiles with realistic joint constraints: no theory certificate without a provisional licence; PIP and accessibility status sampled conditionally rather than independently.
2. Add age as an explicit weighting dimension or generate several personas per answer combination across age bands. Learner-driver test candidates are strongly age-skewed, while the current 16 profiles contain arbitrary ages from 17 to 80.
3. Obtain GOV.UK page analytics or a learner-driver survey to replace transaction-volume stage proxies.
4. Report sensitivity bands by rerunning with accessibility `yes` at 0.08 and 0.16, and PIP mobility `yes` at 0.005 and 0.03.
5. Keep the car-only scope separate from a broader driving-services evaluation; the placeholder v1 `q_main_goal` distribution mixed unrelated journeys.

## Sources

- GOV.UK journey: https://www.gov.uk/learn-to-drive-a-car
- DVLA first provisional applications, 1993-2014: https://assets.publishing.service.gov.uk/media/5a75b968e5274a545822dbc8/The_number_of_First_Provisional_Driving_Licence_Applications_1993_to_2014.pdf
- DfT/DVSA test volumes, Jul-Sep 2024: https://www.gov.uk/government/statistics/driver-and-rider-testing-and-instructor-statistics-april-to-september-2024
- ONS disability by age and sex, Census 2021: https://www.ons.gov.uk/peoplepopulationandcommunity/healthandsocialcare/disability/articles/disabilitybyagesexanddeprivationenglandandwales/census2021
- GOV.UK theory-test accessibility support: https://www.gov.uk/theory-test/reading-difficulty-disability-or-health-condition
- DWP PIP statistics to Oct 2025: https://www.gov.uk/government/statistics/personal-independence-payment-statistics-april-2013-to-october-2025/personal-independence-payment-official-statistics-to-october-2025
