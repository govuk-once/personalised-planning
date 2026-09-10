# Evaluating service-graph against the GOV.UK Knowledge Graph

### Findings from two life events: Driving, and Having a Baby

---

## Summary

We compared service-graph — the curated map of government services that powers our planning agent — against subgraphs of the GOV.UK Knowledge Graph for two life events. The aim was to understand where service-graph is strong, where it is incomplete, and how far its content can be trusted.

**Key findings**

**1. Coverage is partial, and varies a lot by life event.** Service-graph contains 15% of the GOV.UK content the driving subgraph considers relevant, and 33% for having a baby. The gaps are not random: driving is missing the *manage your booking* half of the test journey (check, change, cancel), while having a baby is missing almost all **employment rights** content — service-graph models what a new parent is paid, but not what they are entitled to at work. It is worth noting that while actual node coverage is low, service-graph likely incorporates content from the missing nodes directly in its node metadata. For example `/vehicle-insurance` is not present in service-graph, but refererenced as condition for `dvla-vehicle-tax`. So, the content often exists; it's just not directly linked to a GOV.UK source page.

**2. Where service-graph has content, it is mostly accurate — but financial facts go stale.** Driving scored 91% accuracy on checkable claims (rising to roughly 93–94% after we reviewed the LLM judge's own errors). Having a baby scored only 68%, and the cause was concentrated rather than diffuse: service-graph is holding the previous tax year's statutory rates. Statutory Maternity Pay is recorded as £187.18 a week when it has been £194.32 since April 2026, and the same lag affects Paternity Pay, Shared Parental Pay, Maternity Allowance, Child Benefit and Guardian's Allowance.

**3. The single highest-risk error found was a deadline, not a rate.** Service-graph records a 3-month claim window for the Sure Start Maternity Grant; the actual window is 6 months. The wrong figure appears in seven fields of that one service. Eligible parents could miss out on a £500 payment.

**4. The two life events have opposite weaknesses, which suggests two different kinds of maintenance are needed.** Driving is broad but shallow: many gaps, high accuracy. Having a baby is well-built but stale: good coverage and structure, out-of-date contents. A process that only expands coverage would leave the second problem untouched.

---

## 1. What we compared

**service-graph** is a hand-curated map of government services built for the planning agent by human expert with support from AI. Each node is a *service* — something a person does — with structured fields covering eligibility, costs, contact details and the steps an agent should walk someone through. Nodes are connected by typed edges (`REQUIRES` for genuine prerequisites, `RELATED` for looser association). Services are grouped into life events, and it deliberately includes things GOV.UK does not treat as part of the topic: hardship support, devolved benefits, and NHS services that sit outside GOV.UK entirely.

**The GOV.UK Knowledge Graph** is an automatically generated record of what exists on GOV.UK and how pages link to one another. It is an inventory of *content*, not of services, and it is comprehensive within its remit in a way service-graph is not. The Knowledge Graph is updated on a daily basis and is hosted in BigQuery tables in a Google Cloud project.

For each life event we extracted a **subgraph** — the driving subgraph and the having a baby subgraph — by crawling outward from a set of seed pages and pruning by document type. These subgraphs are the benchmark against which service-graph was measured.

Neither service-graph or subgraph is authoritative. They are built for different purposes, and disagreement between them is usually informative rather than evidence that one is wrong.

---

## 2. Method

Two independent passes were run over each life event.

**Deterministic comparison.** Nodes are matched by normalised GOV.UK path, in tiers: exact path match first, then parent/child relationships where GOV.UK documents at a different granularity to service-graph. Matched nodes give a coverage figure. Unmatched GOV.UK pages are then triaged by rule into categories — `candidate_service` (probably deserves its own node), `lifecycle_satellite` (a more granular view of a service already modelled), `reference_content`, `contact_or_complaint`, `cost_information` — so that the raw gap can be separated from the actionable gap. Edges between matched nodes are compared for agreement.

**LLM-as-judge.** Every factual claim in a matched service-graph node — each eligibility rule, rate, deadline, phone number, service type — is put to a model alongside the text of the corresponding GOV.UK page, which returns one of three verdicts: **supported**, **contradicted**, or **not stated** (the page neither confirms nor denies it). Accuracy is calculated over decidable claims only, i.e. supported ÷ (supported + contradicted). The proportion of claims that were decidable at all is reported separately as coverage.

**Manual re-review.** Every contradiction was then re-examined by hand against the source page, and in some cases against current published sources. This matters: the judge produced false positives in both runs, and the headline accuracy figures move slightly once they are removed.

---

## 3. Node completeness

### Coverage

| | Driving subgraph | Having a baby subgraph |
|---|---|---|
| Pages retrieved | 92 | 31 |
| Excluded as noise | 6 | 1 |
| GOV.UK pages considered | 86 | 30 |
| Matched to service-graph | 13 | 10 |
| Missing | 73 | 20 |
| **Coverage** | **15.1%** | **33.3%** |

Having a baby is roughly twice as well covered. The gap is also smaller in absolute terms — 20 missing pages against 73.

One caveat sharpens the difference further. The driving run allowed matches against all 246 service-graph nodes, while the baby run restricted matching to the 49 nodes in that life event. Driving therefore had the more permissive matching rules and still returned the lower figure, so the difference between the two is real and, if anything, understated.

The reason driving needed those permissive rules is itself part of the finding. Its own life event resolves to only 7 nodes, so matching within it would have been unusable. The 15.1% figure is therefore best read as how much driving content service-graph holds anywhere, not how much of the driving journey is modelled — measured against the declared life event alone, only 5 of the 86 GOV.UK pages have a counterpart.

### Quality of the matches

Driving's 13 matches were all exact path matches. Twelve are unambiguous DVLA or DVSA content. The thirteenth, **Find a job**, is a generic DWP job-search service that entered the driving subgraph through a single tangential link from an HGV qualification page ("here is where to find driving jobs"). It almost certainly belongs to an employment life event. On a stricter reading, driving coverage is 12 of 86 — 14.0%.

Having a baby produced nine clean matches plus one that resolved incorrectly due to presence of duplicate nodes in the service-graph, which is explained under Limitations. Its ten matches include the first use of a non-exact tier: GOV.UK's combined *Maternity pay and leave* guide mapped onto service-graph's pay-only node. Reasonable, but it does mean service-graph has no node for maternity *leave* as distinct from *pay*.

### What is missing, and how much of it matters

The triage step separates the raw gap from the actionable one, and the two life events differ considerably:

| | Driving | Having a baby |
|---|---|---|
| Missing pages | 73 | 20 |
| `candidate_service` (worth adding) | **37 (51%)** | **18 (90%)** |
| `lifecycle_satellite` | 16 | 1 |
| `reference_content` | 12 | 1 |
| `contact_or_complaint` | 5 | — |
| `cost_information` | 3 | — |

Driving's 73-page gap initially looks large, but around half of it can be disregarded on inspection — reference material, contact pages, cost lookups, and alternative views of services already modelled. Having a baby's gap is smaller but almost entirely substantive: 18 of 20 are services one would genuinely want in the graph.

**Driving — the dominant theme is the service lifecycle.** Service-graph models booking a theory or driving test, but not checking, changing or cancelling one. Those follow-on pages are among the most heavily linked in the whole driving subgraph — *Change your driving test appointment* has the highest inbound link count of any missing page. The triage classifies them as satellites rather than gaps, given that GOV.UK splits one service across several URLs (e.g. prefixes `check/`, `change/`, etc) while service-graph deliberately models it as one node. But checking the anchor nodes themselves, their agent-facing step fields cover only the booking action. So the node-count gap is arguably not real while the **functional** gap is: the agent currently has no content to draw on for someone who needs to move a test date. Secondary themes are licence categories and codes, and motorcycle, HGV and towing content, most of which was set aside as being non car focused.

**Having a baby — the dominant theme is employment rights.** Eight of the 18 candidates concern the workplace: employment contracts, rights while on leave, pregnant employees' rights, flexible working, resolving a workplace dispute, unpaid parental leave, and the employer-facing guidance and calculator. Beyond that: **three whole statutory schemes are absent** — Neonatal Care Pay and Leave, adoption pay and leave, and Bereaved Partner's Paternity Leave — which are peers of the four schemes already modelled and therefore clean additions rather than restructuring. Three registration variants are missing (stillbirth, birth abroad, find a register office), along with two eligibility-checking tools.

### Content service-graph has that GOV.UK does not

The comparison runs in both directions, and the reverse direction is mostly *not* a defect. In the baby life event, 40 of 49 service-graph nodes had no counterpart in the subgraph. Ten are off-platform by design — NHS entitlements and Scottish and Welsh devolved benefits that sit outside GOV.UK altogether. Most of the rest form a deliberate **hardship and childcare** cluster: Universal Credit, Budgeting Loans, Council Tax Reduction, debt relief options, court fee remission, free childcare hours. GOV.UK's *having a baby* section does not link to these because they are not *about* having a baby; service-graph includes them because a new parent under financial pressure may well need them.

---

## 4. Edge completeness

Edges were compared only between nodes that both graphs contain.

| | Driving | Having a baby |
|---|---|---|
| Comparable nodes | 13 | 9 |
| Edges in the subgraph | 2 | 5 |
| Edges in service-graph | 6 | 6 |
| Agreed by both | 1 | 2 |
| service-graph only | 5 | 4 |
| Subgraph only | 1 | 3 |
| Overlap (Jaccard) | 14.3% | 22.2% |

Agreement is low in both, and better for having a baby. The agreed edges are, encouragingly, the important ones: driving's single agreement is *driving test requires theory test*, and having a baby's two are *register the birth → Child Benefit* and *Maternity Allowance → Shared Parental Leave* — in each case the backbone of the journey.

Two observations are worth more than the percentages.

**Some service-graph edges look loose.** Driving asserts *vehicle tax → driving test* and *vehicle sale → vehicle tax* as related; the subgraph supports neither. "Vehicle tax relates to driving test" reads more like topical adjacency than a real relationship a planner should act on.

**Edge typing is inconsistent between life events.** Driving uses both `REQUIRES` and `RELATED`. Having a baby uses **only `RELATED`** — not a single prerequisite edge — despite real prerequisites existing, such as registering a birth before claiming Child Benefit, or curtailing Statutory Maternity Pay before Shared Parental Pay.

These figures should be read with the constraint in Limitations below firmly in mind: they are severely restricted by the coverage gap and considerably understate the subgraph's real connectivity.

---

## 5. Accuracy

| | Driving | Having a baby |
|---|---|---|
| Node claims assessed | 151 | 155 |
| Supported | 68 | 81 |
| Not stated | 76 | 35 |
| Contradicted | 7 | 39 |
| **Proportion decidable** | **49.7%** | **77.4%** |
| **Accuracy as reported** | **90.7%** | **67.5%** |
| **Accuracy after re-review** | **~93–94%** | **~70%** |

### Driving: high accuracy, low verifiability

Only half of driving's claims could be decided at all — 76 of 151 were neither confirmed nor denied by the GOV.UK page. That is not necessarily a fault; service-graph deliberately holds agent-facing detail that GOV.UK does not state in those terms. But it does mean the 91% figure rests on a narrower base than it appears to.

Manual re-review found **five of the seven contradictions genuine and two false**. The genuine ones cluster tightly: three are the same underlying error, where service-graph claims an online option exists for changing the name on a driving licence when the process is postal only — a claim contradicted by the node's own linked form. A fourth invents a three-month legal deadline for updating an address that does not exist on the page. The fifth misclassifies a vehicle lookup service as an application.

The two false positives both stemmed from the judge treating "Great Britain" and "England, Wales or Scotland" as conflicting, when the former is the correct legal term for exactly the latter. Removing them lifts accuracy to roughly 93–94%.

### Having a baby: lower accuracy, but far better evidenced

The 67.5% figure is a substantial regression — and note that it rests on a **much stronger base**, with 77% of claims decidable against driving's 50%.

It is also concentrated rather than diffuse. Three clusters account for 24 of the 39 contradictions:

**Stale statutory rates — 14 contradictions.** Service-graph holds 2025/26 figures; the subgraph holds 2026/27, uprated in April 2026. Verified against current published sources:

| | service-graph | Correct |
|---|---|---|
| Maternity / Paternity / Shared Parental Pay, Maternity Allowance | £187.18/week | **£194.32/week** |
| Child Benefit, eldest child | £26.05/week | **£27.05/week** |
| Child Benefit, other children | £17.25/week | **£17.90/week** |
| Guardian's Allowance | £21.75/week | **£22.95/week** |
| Lower Earnings Limit | £123/week | **£129/week** |

The last is two tax years behind rather than one. This is one systematic failure, not fourteen independent errors, and it drags the `financialData.rates` field to 11% accuracy — the worst of any field in either life event.

**The Sure Start Maternity Grant deadline — 7 contradictions.** One wrong value, 3 months instead of 6, replicated across seven fields of a single service.

**Paternity leave timing — 3 contradictions.** Service-graph carries an "arrange before the baby is 8 weeks old" rule; the current rule is that leave must be taken within 52 weeks of birth, and paternity leave became a day-one right in April 2026.

Individually confirmed errors beyond these clusters include birth registration described as covering England and Wales when it covers Northern Ireland too, Child Benefit flagged as having no eligibility test when it has both a responsibility and a residency test, an incorrect helpline number shared by two services, and a baby loss certificate service that omits surrogates.

### On the judge itself

Re-review found the judge is directionally reliable but not fully precise. Across both runs it produced clear false positives .
This means that judge output should be treated as a first pass verification attempt to be followed by a human review.

---

## 6. Limitations

### Of service-graph

**Node reachability.** In its current implementation, a node belongs to a life event if it is reachable by following edges outward from that life event's entry nodes. Membership is therefore a consequence of how the graph happens to be wired, and a genuinely relevant service that is not edge-connected will be silently excluded.

Driving is the clearest illustration. The driving life event is named Learning to Drive, has two entry nodes, and resolves to just 7 services. Yet service-graph holds 17 nodes owned by DVLA or DVSA — renewing a licence, renewing at 70, changing a name or address, notifying a medical condition, viewing a licence, checking MOT history and others all exist as nodes but sit outside the journey. Whether that is deliberate scoping — the life event is learning to drive, not driving generally — or an oversight is unresolved. Either way, a planner traversing the driving life event as modelled would never reach two thirds of the driving content service-graph contains.

**Several nodes claim the same GOV.UK page.** Five paths in service-graph are claimed by more than one node, covering twelve nodes in total. Some are deliberate and sensible — 15 hours and 30 hours free childcare are distinct services documented on one page. Others look like genuine redundancy: three separate nodes claim the birth, death and marriage certificate page. This has real consequences, discussed below.

**Time-sensitive content has no expiry.** Rates, thresholds and deadlines sit in the graph as plain values with no indication of which tax year they apply to. Nothing in the system signals that a figure has gone stale.

**Services are modelled at the point of application, not across their lifecycle.** The agent-facing step fields on the driving test, theory test and provisional licence nodes describe only how to apply or book. Nothing covers checking, changing or cancelling.

**Edge properties are applied inconsistently** across life events, as noted above.

### Of the comparison method

**The two runs are not fully comparable.** Driving matched against all 246 service-graph nodes; having a baby matched only within its 49-node life event. Coverage remains comparable — and the difference favours having a baby even so — but any precision-style figure does not.

This divergence was closer to forced than chosen. Restricting the driving run to its own life event would have left only 7 candidate nodes, so matching against the full graph was the only way to get a usable result.

**Node matching is one-to-one and resolves clashes arbitrarily.** Where several service-graph nodes claim the same path, the matcher picks one with no preference for in-scope candidates. In the baby run this produced a wrong answer: the GOV.UK certificates page was matched to *Obtain death certificates* rather than to *Order a birth, death or marriage certificate*, which is not only the better match but an explicitly declared entry node of that life event. The single error produced three downstream artefacts — a false match, a false out-of-scope flag, and the correct node being reported as never reached by the crawl. Correcting it moves baby coverage from 30% to 33.3%. The method also cannot represent the legitimate case where one page corresponds to several services.

**Edge comparison is severely constrained by the coverage gap.** An edge is only counted when *both* ends are matched nodes. In the baby subgraph, matched nodes are touched by 26 edges, but only 5 survive that restriction — around 80% of the relevant connectivity is invisible. Driving is worse still: 2 of roughly 74. **The low edge agreement figures are largely an artefact of the coverage gap, not evidence that GOV.UK's pages are poorly linked.** They will improve as coverage improves, independent of any change to edge modelling.

**The subgraph boundary is set by crawl radius.** What counts as "in scope for driving" is determined by how far the crawl travelled and which document types were pruned — a defensible but arbitrary line, which is how a generic job-search page came to be judged as driving content.

**"Not stated" is the largest single verdict category** in the driving run and a substantial one in the baby run. These claims are neither validated nor invalidated, so a meaningful share of service-graph's content is simply untested by this method.

**Triage roles are assigned by pattern-matching on page titles and URLs**, not by meaning. It is a reasonable first pass that is known to misfire on similarly-named pages, and it is unrelated to graph position despite the two correlating in practice.

**Off-platform nodes can never match** — NHS and devolved services are absent from the Knowledge Graph by definition, so they permanently count against service-graph in one direction of the comparison.

**Knowledge Graph edge types were unavailable** in both runs, so edges could only be compared on presence, never on whether the two graphs agree about the *nature* of a relationship. This is an oversight of not retaining `link_type` property from the full Knowledge Graph content in Google Cloud.

---

## 7. Conclusion

Across two life events, service-graph looks like a **high-precision, low-recall** artefact: what it contains is largely correct, and there is considerably less of it than the equivalent GOV.UK content. That is appropriate for a curated graph, but it imposes constraints on the analysis and validation of the service-graph content.

The two life events differ in how their subgraphs compare to the service-graph. Driving is **wide and shallow** — a 73-page gap of which about half is substantive, high accuracy on what exists, and a systematic blind spot around managing a service after you have started it. Having a baby is **narrow and stale** — well covered, well connected, but with a tax year's drift in its numbers and one materially wrong deadline. A coverage-focused programme would fix the first and leave the second entirely intact.

Three things generalise beyond these two life events:

**Structured facts decay on a schedule, and nothing currently tracks it.** The April uprating is predictable, annual, and affects every benefit and statutory payment in the graph. Having a baby was the life event where it showed up first because it is dense with rates, but there is no reason to expect other life events to be exempt — they simply have not been checked.

**Coverage and connectivity cannot be measured separately.** The edge figures in this report are largely a shadow of the node gap. Until coverage improves, edge agreement is not measuring what it appears to measure, and low values should not be read as a structural finding about either graph.

**The differences between the two graphs are often driven by decision decisions.** Service-graph deliberately reaches beyond GOV.UK into hardship support, devolved benefits and NHS services, and deliberately collapses several GOV.UK pages into single services. Both choices look like failures when measured against the Knowledge Graph and are defensible in their own terms. Any ongoing metric will need to hold that distinction, or it will steadily push service-graph towards being a copy of GOV.UK's structure rather than a model of how people engage with services.

Finally, this evaluation is a useful instrument but not a precise one. The judge produced false positives in both runs; a data collision produced a wrong match; the subgraph boundary is somewhat arbitrary; and roughly half of driving's claims could not be tested at all. The findings that survived manual re-review — the coverage shape, the stale rates, the Sure Start deadline, the employment rights gap — are solid. The percentages around them should be treated as directional.
