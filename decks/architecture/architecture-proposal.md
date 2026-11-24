# Personalised Planning: architecture today and proposed changes

Status: draft proposal, 24 November 2026. This document goes with the slides in `architecture.pptx` and `architecture.html`. Slides 2 to 4 show the service today and slide 5 shows the proposal.

## Summary

Today one web frontend talks to one backend, which runs every agent call as an async job. A conversation agent gathers facts about the user. When it has enough, the user presses Start plan and the frontend passes those facts to a planner agent.

The proposal makes four changes:

1. **A second frontend.** A React Native GOV.UK app joins the web frontend. Both call one new public API.
2. **Users are identified.** An identity provider signs users in, and the API checks their token, so plans can be saved and fetched per user (to be actioned later).
3. **Plans get their own backend** with two endpoints: one to generate a plan and one to get a user's plans.
4. **Chat V2 replaces the conversation agent.** It's an orchestrator that gathers context and, when the user presses Start plan, calls the plans backend itself. Its internal design is to be confirmed.

The planner agent, Claude on Bedrock, AgentCore Gateway and the service graph stay as they are.

## The service today

### Containers (slide 3)

| Container | Technology | What it does |
|---|---|---|
| Frontend | Next.js 16 on Amplify | Pages in the browser. Server actions call the backend. |
| Api | Node.js Lambda | `start_chat` and `start_plan` save a pending job and start the Worker. `get_job` returns the job for polling. |
| Worker | Node.js Lambda | Claims the job, calls the agent on AgentCore Runtime, and saves the reply or marks the job failed. |
| Jobs table | DynamoDB | One record per job: status, then the agent's reply. |
| Conversation agent | Python, Strands, AgentCore Runtime | Asks the next question and collects facts until it has enough. |
| Planner agent | Python, Strands, AgentCore Runtime | Turns the situation and facts into a step-by-step plan. |
| Claude | Bedrock, eu-west-2 | The model both agents use. |
| AgentCore Gateway | AgentCore | The MCP endpoint the agents use to reach the service graph. |
| Service graph | TypeScript MCP server on Lambda | Five tools over the UK government services graph. |

The frontend never calls an agent directly. Every agent call is a job: the frontend starts it, then polls until the Worker saves the reply. This keeps long agent calls off the web request and makes failures visible as job states.

### Experience flow (slide 2)

1. The user describes their situation.
2. The conversation agent asks one question per turn, up to N. Each turn returns the next question, the facts collected so far and a `complete` flag.
3. When complete, the agent sums up the conversation in one sentence (`situation`).
4. The page shows a Start plan card. When the user presses it, the frontend sends `situation` and the collected facts to `start_plan`.
5. The planner builds its prompt from those ([planner_logic.py](../../agent/app/planner_logic.py)) and returns the plan.

The context travels through the client and is held in the browser's `sessionStorage`. The planner never sees the transcript.

### Components (slide 4)

Slide 4 opens each container up. File-level detail is in its speaker notes.

### How it's deployed today

| Part | Deployed by |
|---|---|
| Api, Worker, jobs table, compute role | Amplify Gen 2 CDK (`amplify/jobs-backend/`) |
| Observability dashboards | Amplify Gen 2 CDK (`amplify/observability/`) |
| Planner and conversation runtimes | AgentCore CDK from `agentcore/agentcore.json` |
| Service graph Lambda, AgentCore Gateway, their IAM roles | **By hand**, using the steps in `mcp-servers/service-graph/README.md` |
| Frontend | Amplify Hosting |

`agentcore.json` declares no gateways or memories today (`agentCoreGateways: []`, `memories: []`).

## The proposed architecture (slide 5)

### What's new, changed and unchanged

| Container | Status | Notes |
|---|---|---|
| GOV.UK app | New | React Native. It can't use Next.js server actions, so it needs a public API. |
| Web frontend | Changed | Calls the public API in place of invoking the Api Lambda. |
| Identity provider | New | Generic for now. Signs users in. The API checks the user's token. |
| Public API | New | API Gateway in front of the backends. One entry point for both frontends. |
| Chat V2 agent/orchestrator | New, replaces the conversation agent | Gathers context, and starts plan generation when the user presses Start plan. Design to be confirmed. |
| Generate plan | New endpoint | Called by the orchestrator, not the client. Saves a pending plan for the user and starts the plan worker. |
| Plan worker | Changed | Calls the planner agent and saves the finished plan. |
| Plan store | New | Plans kept by user. Technology not chosen yet. |
| Get plans | New endpoint | Returns the user's plans. Used to poll a plan being generated and to show saved plans. |
| Planner agent | Unchanged | Stays on AgentCore Runtime. |
| Claude, AgentCore Gateway, service graph | Unchanged | Both agents use them as today. |

### Request flows

**Conversation.** The client sends each user message through the public API to Chat V2. How Chat V2 runs turns (synchronously, or with jobs and polling as today) is to be confirmed.

**Starting a plan.** When Chat V2 judges it has enough, the user sees the facts collected and a Start plan button. Pressing it tells the orchestrator, which calls Generate plan with:

- the user's identity
- the situation summary
- the structured facts, against an agreed, versioned schema

Generate plan saves a pending plan with that context and starts the plan worker. The client never carries the facts, and the transcript stays in Chat V2.

**Getting plans.** The client polls Get plans until the new plan is ready, and uses the same endpoint later to list the user's saved plans.

### Why the orchestrator calls Generate plan

We considered four ways to pass context from chat to the planner:

| Option | For | Against |
|---|---|---|
| Client relays it (today) | Simple, stateless | Client can change facts. Both frontends must carry them. Facts sit on the device. |
| Server-side context record, passed by ID | Trusted. Small requests. Plans traceable to their context. | Needs a shared store and schema. |
| **Orchestrator calls Generate plan (chosen)** | One flow for clients. Fits an orchestrator. Facts never leave the server. | Couples chat to plans. Plan generation must stay async. |
| Event when context is ready | Most decoupled | Harder to show progress and handle failures. Most moving parts. |

We keep an explicit Start plan step, so the user sees and confirms the facts before a plan is made.

## Replacing the conversation agent with the Chat V2 orchestrator

### What Chat V2 does

Chat V2 replaces the conversation agent as the single agent the user talks to. It:

1. **Gathers context.** It asks questions, collects structured facts, and decides when it has enough to plan.
2. **Shows the user what it has.** It presents the facts for confirmation, with the Start plan button.
3. **Calls tools when needed.** On Start plan it calls the tool to generate a plan, which wraps the Generate plan endpoint. It may also use a `get_plans` tool to talk about plans the user already has.
4. **Keeps the conversation history**, which never leaves Chat V2.

### Tools it would need

| Tool | Calls | When |
|---|---|---|
| `[generate_plan]` | Generate plan endpoint | When the user presses Start plan |
| `get_plans` | Get plans endpoint | To answer questions about existing plans (to be confirmed) |
| Service graph tools | AgentCore Gateway | To ground and guide context gathering (see below) |

### Using the service graph to gather context

It's not yet clear how Chat V2 should use the planning resources, but it will probably need them. A plan is only as good as the facts behind it, and the graph knows which facts each service depends on.

The current conversation agent already has two ways to choose questions, set by `QUESTION_SOURCE` in [chat_agent.py](../../agent/chat/chat_agent.py):

- **From the graph:** it calls `get_required_information`. Given the life events, that tool returns a deduplicated checklist of questions, each with the field to store the answer under.
- **Static:** a fixed question set in [questions.json](../../agent/chat/questions.json), with no MCP call. This is defunct and should be removed.

Ways Chat V2 could use the graph, which can be combined:

| Approach | Graph tools | What it gives |
|---|---|---|
| Scope the situation first | `list_life_events` | Maps what the user says to one or more of the 16 life events, so questions stay relevant |
| Ask what the journey needs | `get_required_information` | The questions the services depend on, deduplicated, with stable field names |
| Prune questions as answers arrive | `check_eligibility` | Skips questions for services the user can't use |
| Explain services in conversation | `get_service` | Lets the agent answer "what is this?" without starting a plan |
| Generate question sets offline | Graph data | Fixed, reviewable question sets per life event, as in today's static mode, built from the graph |

The field names the graph returns should become the facts schema that Chat V2 sends to Generate plan. That links the two agents through a shared model, not through prose.

### Things to get right

- **Plan generation stays async.** Chat V2 should start the plan and return straight away, not wait for the planner inside a chat turn.
- **Start plan is enforced in code, not in the prompt.** `generate_plan` works after a real Start plan action, so text in a user's message can't trigger it. This may change in future based on updated designs, but is the current assumption.
- **Service-to-service auth.** Chat V2 calls Generate plan on the user's behalf. Agree how it proves both its own identity and the user's.
- **Store as few facts as possible.** Pass facts, not the transcript. Decide how long the conversation history and the plan context are kept.
- **Turn limits.** Today's N-question cap cannot carry over to Chat V2. Should it be replaced by a rule the graph drives?

### Moving over

1. Build Chat V2 as a new AgentCore runtime alongside the conversation agent. Renaming a runtime in `agentcore.json` destroys and recreates it, so add a new one.
2. Agree the facts schema with the planner side, starting from today's `collected_facts` and the graph's field names.
3. Run both behind a flag, and compare plan quality with the existing evaluation scripts.
4. Remove the old runtime with `agentcore remove`.
5. App frontent to come later.

### Open questions

- How does Chat V2 run turns: synchronously?
- Does it hold conversation state in AgentCore Memory, a table, or the request?
- Which service graph tools should it use, and in what order?
- Does it read existing plans (`get_plans`), or only create them?
- What does the user see when generation fails or the facts change after a plan exists?
- [add questions here]

## Infrastructure as code requirements

Everything in the proposed architecture must be defined in CDK (eventually).

### General

- **Every resource in CDK**, including those deployed by hand today: the service graph Lambda, AgentCore Gateway and their IAM roles.
- **Clear ownership of stacks.** Today two CDK apps share the work: Amplify Gen 2 for the backend, and the AgentCore CDK for agent runtimes. Should we keep AgentCore resources (runtimes, gateway, memory) in `agentcore.json`, and application resources (API, Lambdas, stores) in the application CDK app? 
- **Values passed between stacks, not copied.** Stack outputs, such as the gateway URL, runtime ARNs and the API URL, reach the other stacks and the runtimes through SSM Parameter Store or CDK references. Replace values typed by hand, such as `GRAPH_GATEWAY_URL`?
- **Environments from one definition.** The same code deploys every environment and branch environment, with differences in config only. Branch environments can be torn down cleanly.
- **Region and data.** Everything in eu-west-2. Encryption at rest on every store. Log retention set explicitly.
- **Tagging.** Every resource tagged with component and branch, extending today's `pp:component` and `pp:branch` tags.
- **Least privilege.** Each Lambda and runtime gets only the permissions it needs, defined in CDK, with no wildcard actions.
- **Checks on every pull request.** CI runs `cdk synth`, `agentcore build` and `cdk diff`, and the diff is reviewed before deploy. Deploys run from the pipeline, not from laptops.

### By component

| Component | Requirements |
|---|---|
| Public API | API Gateway with routes for Chat V2, Generate plan and Get plans. JWT authoriser for the identity provider. Throttling and usage limits. CORS for the web frontend. WAF. Custom domain and certificate. Access logs. |
| Identity provider integration | Issuer, audience and client IDs as config per environment. Any client secrets in Secrets Manager, never in code. |
| Chat V2 orchestrator | A new runtime in `agentcore.json`. AgentCore Memory, if used, declared there too. Permission to call Generate plan and Get plans, and to call Bedrock and the gateway. Environment variables set from stack outputs. |
| Generate plan, Get plans, plan worker | Lambdas in the application CDK app. Async invoke of the worker, with a failure destination or dead-letter queue. A concurrency cap, like today's `MAX_WORKERS`. A timeout below the agent's. |
| Plan store | Defined in CDK whatever the technology. Keyed by user. Point-in-time recovery or backups. A retention rule agreed with information governance. |
| Planner agent | The existing runtime in `agentcore.json`, unchanged, with permission for the plan worker to invoke it. |
| AgentCore Gateway | Moved into `agentcore.json` under `agentCoreGateways`, with a `lambda` target, tool schemas and its IAM role. Its URL published for both agents. |
| Service graph Lambda | Built and deployed by the pipeline from `mcp-servers/service-graph`, replacing the manual zip-and-upload steps. Runtime and memory set in CDK. |
| Web frontend | Amplify Hosting stays. Config points at the public API and identity provider. Remove the compute role's direct Lambda invoke once the API is live. |
| GOV.UK app | Not AWS infrastructure. CDK publishes what the app needs: the API URL and identity settings per environment. |
| Observability | Dashboards, log groups, traces and alarms for every new component, extending `amplify/observability/`. Alarms on API errors, worker failures, plan generation time and Bedrock throttling. |

## Not covered

Evaluation scripts, synthetic profile generation and other tooling outside the running service are left out of this document and the slides.
