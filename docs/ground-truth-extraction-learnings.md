# Personalised Planning Evaluation
## What data structures do we need to power the planner agent and evaluate its outputs?

### Summary

We tested whether step by step guides for life events can be generated programmatically from GOV.UK content without content designer input. We used "Having a baby" as the test case, scoped to a typical journey (natural pregnancy, single live birth in the UK, no neonatal care, no bereavement). Our pipeline turned ~1,900 sentences of GOV.UK content into ~170 typed draft tasks. These were reviewed and reconciled into 122 tasks, 85 of which were then selected for a step by step guide for the typical journey. So far the results have been reviewed by the data scientists with LLM assistance (Claude Opus 5). An information architect is reviewing how the information is presented; the content itself has not yet been checked by a content or subject matter expert. We intend to use the guide as an internal reference for evaluating generated plans for “Having a baby”.

**The process for generating guides is semi-automatic, not automatic.** Automation handled the detection and parsing of GOV.UK content containing tasks, and LLMs performed well at turning unstructured text into structured draft tasks. However, human review and judgement were required at every key decision: what is in scope, which user groups and branches to cover, and whether two draft tasks are duplicates, alternatives, or one task that should be split. For a single branch of one life event, and excluding the content desigher review, this work took three iterations and roughly 6 days in total, of which ~95% was human review and reconciliation rather than pipeline build. The step by step guide and the list of tasks that underpins it will also require ongoing maintenance, because tasks carry metadata such as rates, deadlines and eligibility that change. So producing a guide entails both build and regular update costs.

This has implications for how we design the planner agent. If the agent relied on an approved step by step guide for every life event (see Option 2 below), the human effort would multiply with every life event, branch and user group. That approach also does not seamlessly support a citizen whose needs span several life events. If the agent relied on search alone (see Option 1 below), we would not need an underlying data structure. But plans would be slower and cost more, because the agent makes many more tool calls to gather and synthesise relevant government content. They would also vary more, because the agent has more discretion over which actions to include. [Early testing](https://github.com/MaxwellRiess/UK-Gov-Service-Graph-poc/blob/main/docs/experiment-results-trial3.md) also suggested search was no better on precision and recall than a purpose-built structured graph of government services (the service-graph). The middle path looks best (see Option 3 below): a structured service-graph that the agent queries and turns into a personalised plan.

**Recommendation**: invest in the existing service-graph rather than in generating step by step guides for every life event. In particular: review the schema, add a layer of citizen-facing tasks linked to services, and use structured sources (GOV.UK Knowledge Graph, Content API) to check and refresh the graph, with a record of the evidence behind each fact. We will keep the generated "Having a baby" guide as an internal evaluation reference.

---

### Background

We ran this investigation for two reasons:
- **Primary:** step by step guides are the best pre-existing canonical reference we have for evaluating the plans an agent produces.
- **Secondary:** a canonical step by step guide could be used by the planner agent directly.

Step by step guides do not exist for all life events. Producing an official one usually takes a lot of content designer effort and coordination with the relevant departments.

**Scope of the trial.** "Having a baby", covering tasks for a `birth_parent`, a `partner`, or `either_parent`: natural pregnancy, single live birth in the UK, no neonatal care, no parental bereavement.

**Approach.** We extracted content programmatically from the GOV.UK Knowledge Graph (Content API data, crawled from the Pregnancy and birth browse page). We used LLMs to synthesise and shortlist tasks. The data scientists reviewed draft and final tasks with LLM assistance (Claude Opus 5). We went through three iterations.

**Review status.** An information architect is reviewing how the guide presents information, with feedback expected w/c 2 November. We would also like a content designer to review the guide independently. This would test our conclusions on the guide's quality and inform estimates of review effort.

**Implementation details.** Pipeline code is contained in this [PR](https://github.com/govuk-once/personalised-planning/pull/53).

---

### What we learned from generating a step by step guide

#### 1. Where the effort actually goes

The table below summarises effort across 3 iterations. Developing a guide for a new life event will likely require refinements to the existing implementation.

| Stage | What it involves | Automated? | Human input | Up-front or ongoing | Effort (hours) |
|---|---|---|---|---|---|
| 1. Scope and vocabularies | Decide which topics are in scope (e.g. natural birth vs surrogacy, adoption, fostering) and define controlled vocabularies (actors, reference points such as "before birth" or "within 42 days") | No | High. Policy and domain judgement | Up-front per life event; vocabularies partly reusable | [4 h] |
| 2. Retrieve candidate content | Crawl the Knowledge Graph subgraph and pull content items | Yes | Low. Choose the seed pages | Up-front build is reusable; re-run cheaply | [3 h build and iterate] |
| 3. Detect task-bearing content | Find the sentences or elements that describe something a citizen must do | Mostly | Low. Spot-check | Reusable | [2 h] |
| 4. Synthesise draft tasks | LLM turns ~1,900 sentences into ~170 structured, typed tasks | Yes (LLM) | Medium. Prompt and schema iteration, then review of output | Prompt work up-front; review needed on every run | [8 h build and iteration / 18 h review] |
| 5. Reconcile tasks | Decide whether to remove duplicates, merge, split, or tag tasks as alternatives | LLM-assisted at best | High. Needs subject matter expertise | Up-front, and again when content changes | [6 h] |
| 6. Choose user groups and branches | Decide which journeys to model | No | High | Up-front per life event; grows with each branch | [4 h] |
| 7. Shortlist the typical journey | LLM selects and orders the relevant tasks | Yes (LLM) | Medium. Check for missing or extra tasks | Per guide / branch | [2 h] |
| 8. SME review | Expert checks the final guide | No | High | Per guide, and after significant changes | [TBC after this week's review] |

**Pipeline funnel:** ~1,900 sentences → ~1,400 task-bearing → ~170 draft tasks → 122 after reconciliation → 85 in the typical-journey guide.

Key points:
- **Detecting tasks is easy; turning them into clean tasks is not.** Stages 2–3 automate well. Stages 1, 4, 5 and 6 are where the time went, and they are the stages that grow with each new life event.
- **Reconciliation is the bottleneck.** The same obligation often appears on several pages with different wording, scope or actor. Telling true duplicates from genuine alternatives (e.g. claiming Statutory Maternity Pay vs Maternity Allowance) needs domain knowledge. At this stage in our pipeline, 170 structured tasks were reduced to 122 (19 removed as out of scope, 21 dropped as duplicates, 2 split and redistributed, 6 moved to sub-tasks).
- **The final guide is still LLM-produced.** Shortlisting for the typical journey is done by an LLM, so the guide inherits LLM error and needs review.
- **Tasks sit in a natural hierarchy.** Most tasks sit under a higher-level `policy` or `service` (e.g. Statutory Maternity Leave). This suggests tasks should hang off services in the graph rather than live in a separate structure.

#### 2. Up-front vs ongoing effort

**Up-front, per life event**
- Scoping, vocabularies, choice of user groups and branches (human).
- First full run of the pipeline and complete reconciliation (human-heavy).
- Review of the final guide.

**Up-front, one-off (reusable across life events)**
- Crawler, extraction and synthesis pipeline, task schema, prompts.
- Core vocabularies (actors, time reference points) can largely be reused.

**Ongoing, to maintain step by step guides**

*We haven't yet maintained a generated guide over time, so the points below are estimates. The closest evidence comes from the service-graph. Its author refreshed statutory rates and is validating the graph's claims against source content. Building that refresh took a few days, and validation is still ongoing. **[EVIDENCE: ask the service-graph author for hours spent, number of facts checked, and number found stale or wrong.]***
- **Detecting change (automatable).** Watch the Content API for updates to source pages (e.g. `public_updated_at`) and flag the tasks that came from them. This only works if we keep the link from each task to its source content.
- **Refreshing details (partly automatable).** Rates, thresholds and deadlines change, often on a known schedule (e.g. statutory payment rates usually change each April). They can be re-extracted, but a person needs to confirm them. The stale statutory rates and wrong Sure Start Maternity Grant deadline found in the service-graph show what happens without this.
- **Re-reconciling (human).** When a page is restructured, or a policy changes, merge and split decisions may need revisiting. This is the expensive part, and it does not go away.
- **New branches and policy changes (human).** Each new user group or policy needs another scoping and reconciliation pass.

**[EVIDENCE: rough estimate of churn, e.g. how many of the source content items changed in the last 12 months. That tells us how often maintenance would be triggered.]**

**So what:** for one life event, the up-front cost is manageable and the ongoing cost is modest if changes are detected automatically. Across all life events and their branches, both costs multiply. The human work that dominates them (scoping and reconciliation) cannot be automated away.

---

### Implications for the data structure behind the planner agent

| | Option 1: Search only | Option 2: Approved step by step guides | Option 3: Structured service-graph |
|---|---|---|---|
| What the agent does | Searches GOV.UK / Content API and builds a plan | Filters a fixed guide by the user's circumstances | Queries services (and possibly tasks) and builds a plan |
| Agent discretion | High | Low | Medium |
| Build effort | None | Very high, per life event and branch | Medium. One schema, populated incrementally |
| Maintenance effort | None (content is live) | High. Each guide re-reviewed when content changes | Medium. Change detection plus targeted review |
| Spans several life events | Yes | No | Yes |
| Plan consistency | Low | High | Medium–high |
| Efficiency | Poor. More tool calls, more latency and cost | Good | Good |

**Option 1. No data structure; the agent searches GOV.UK or the Content API.** This removes the need to build and maintain anything. But early experiments with the service-graph showed this approach is inefficient: the agent calls search tools much more often, which adds latency and cost, and precision and recall are no better than with the service-graph (see [results from early investigation](https://github.com/MaxwellRiess/UK-Gov-Service-Graph-poc/blob/main/docs/experiment-results-trial3.md)). The agent also has a lot of discretion over which actions to recommend, so plans vary more.

**Option 2. The agent uses approved step by step guides.** The agent has the least discretion: its only job is to filter tasks by the user's circumstances. But as the effort analysis above shows, creating and maintaining guides across all key life events, including branches and user sub-groups, would take a lot of human effort. This option also does not support users whose needs span several life events.

**Option 3. The agent uses a structured data source (tool) holding information about services, and pulls what is relevant.** The agent has a fair amount of flexibility in how it uses the tool and turns information about services and their tasks into a personalised plan. Some of the Option 2 challenges still apply, but they are more tractable. The data is held in a structured, searchable form, but it does not have to be turned into a fixed, ordered set of steps for every journey.

Our trial suggests Option 2 is unlikely to scale across life events, and Option 1 is inefficient and gives the agent too much freedom. That points to Option 3: an improved version of the existing service-graph.

---

### Recommendation

Focus on Option 3 and plan improvements to the existing service-graph proof of concept:
- **Revisit the schema.** Are we modelling the entities we need? Which properties or metadata are missing for better conversational onboarding and planning (e.g. eligibility conditions, deadlines relative to reference points)?
- **Add a layer of citizen-facing tasks**, each linked to its parent service. The task schema and vocabularies from this trial are a starting point.
- **Keep the graph current with evidence.** Use structured sources (GOV.UK Knowledge Graph, Content API) to check and update the graph. Store a source link and a "last verified" date against every fact, so we can detect change automatically and send only the affected items for human review.
- **Keep the generated "Having a baby" guide** as an evaluation reference for generated plans, once SME feedback has been applied. Re-check it against source content before each evaluation round.
- **Share the refresh and validation approach** between the guide pipeline and the service-graph rather than building two. Both need the same change detection and verification of facts against their sources.
