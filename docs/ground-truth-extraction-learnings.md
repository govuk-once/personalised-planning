# Personalised Planning Evaluation
## What data structures do we need to power planner agent and evaluate its outputs?

### Overview
This document summarises learnings from a recent investigation into feasibility of scalably generating step by step guides for life events.

Two reasons for this investigation:
- Primary reason is that step by step guides are ideal references to use in evaluating plans produced by an agent.
- Secondary reason is that a canonical step by step guide can potentially be used directly by a planner agent.

However step by step guides are not available for all life events as producing an official guide typically involves a large amount of effort from content designers and coordination with the relevant departments.

We attempted to programmatically create a step by step guide for having a baby. Specifically, we trialled extracting a long list of citizen facing tasks from GOV.UK content and producing a step by step guide for a typical user journey. This refers to a journey that comprises tasks relevant to a `birth_parent`, a`partner`, or `either_parent` in case of natural pregnancy, single live birth in the UK, no neonatal care, no parental bereavement.

We went through several iterations to refine the approach. In the final implementation we used a combination of programmatic content extraction from GOV.UK knowledge graph, followed by LLM and dev team review. The resulting guide is intended for internal purposes and will only be used to evaluate quality of generated personalised plans.

### Key learnings
Here we list immediate learnings from the exercise of generating a step by step guide. We also comment on implications for a broader question on data structures that should underpin planner agent.

#### What we learned by attempting to generate step by step guide
- Extracting ground-truth tasks from GOV.UK content is feasible at scale as a semi-automatic process, not an automatic one. Extensive human input is needed at multiple stages:
    - defining topics that are in scope (e.g. natural birth vs surrogacy, adoption and fostering) and vocabularies (e.g. actors, reference points)
    - deciding on user groups and branches to focus on
    - reviewing candidate content and draft tasks
    - deciding on how to split, merge or recode draft tasks.
- Detecting content elements that contain tasks is straightforward, synthesising draft tasks from raw content is not. LLMs are required to parse unstructured content (~1,400 sentences) and output a structured typed tasks (~170).
- It is challenging to identify when draft tasks need to be removed as duplicates, merged, split or tagged as alternatives for the same task. Subject matter expertise is required.
- Final step by step guide is still produced by an LLM by shortlisting tasks relevant for a typical user journey.
- There is a natural information hierarchy as tasks often sit under a higher level `policy` or `service` (e.g. Statutory Maternity Leave).
- Tasks carry metadata that would require regular updates to prevent it from going stale

#### Implications for data structure to underpins planner agent
As mentioned above, a canonical step by step guide can be used by the planner agent directly. This is the one of several options for data structures to underpin a planner agent:
1. Option 1: No data structure, agent finds content directly using search GOV.UK or Content API. While this eliminates the need to build and maintain a dedicated data structure, early experiments with the service-graph showed that this architecture is not efficient. Agent ends up calling search tools much more frequently, which adds to latency and cost. The precision and recall are not better compared to using a service-graph [add link to MR's paper]. Another limitation is the high level of discretion agent has in identifying actions for the user. This can lead to higher variability across plans.

2. Option 2: Agent uses approved step by step guides. In this option agent has the least amount of discretion and its only task is filtering tasks based on user circumstances. The trade-off is that creating such guides across all key life events (including branching and user sub-groups) would require a lot of manual human effort. We mentioned some of the resource intensive inputs earlier. It also doesn't address use cases when user needs support across several life events.

3. Option 3: Agent uses a data structure (tool) that contains information about services and agent pulls what's relevent. The agent has a fair amount of flexibility and discretion in how it uses the tool and how it synthesises information about services and associated tasks into a personalised plan. The challenge associated with this option is similar to Option 2. It is more tractable as it stops halfway through storing information in a structured and searchable form but does not translate this content into set of tasks or steps.

Our work on generating a step by step guide programmatically shows that Option 2 is not likely to scale well across life events. We also mention that Option 1 is also not ideal, as it is not efficient and also gives too much freedom to the agent. This means that Option 3 - a modified version of the existing graph seems most promising.

### Recommendation
Focus on Option 3 and plan improvements to the existing service-graph POC:
- Revisit service-graph data schema - are we modelling entities we need? which properties / metadata we are missing to enable a better conversational onboarding and planning?
- Consider adding a layer of citizen facing tasks, which are connected to relevant services.
- Consider which sources of structured content we could use to check and update the graph (e.g. GOV.UK knowledge graph, Content API). How is evidence captured?
