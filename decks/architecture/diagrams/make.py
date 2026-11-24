"""C4 level 2 container diagram for decks/architecture. Run: python3 decks/architecture/diagrams/make.py"""

import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "..", "..", ".claude", "skills", "gds-slides", "scripts"))
from diagram import MUTED, area, box, group, line, strong, svg, text, write  # noqa: E402


def containers():
    s = 11
    g = box(10, 60, 100, 56, "User", "web browser")
    g += line(110, 88, 128, 88)
    g += box(130, 60, 140, 56, "Frontend", "Next.js on Amplify")
    g += line(270, 88, 358, 88) + text(305, 80, "starts, polls", s)

    g += area(345, 10, 175, 340, "Backend")
    g += box(360, 60, 140, 56, "Api", "Lambda")
    g += line(395, 116, 395, 168) + text(401, 147, "saves job", s, anchor="start")
    g += box(370, 170, 120, 56, "DynamoDB", "jobs table")
    g += line(395, 270, 395, 228) + text(401, 252, "saves reply", s, anchor="start")
    g += box(360, 270, 140, 56, "Worker", "Lambda")
    g += line(492, 116, 492, 268) + text(488, 158, "starts", s, anchor="end")

    g += line(500, 298, 558, 298) + text(540, 290, "calls", s)
    g += area(560, 170, 270, 180, "AgentCore Runtime")
    g += strong(580, 205, 230, 56, "Conversation agent", "asks the next question")
    g += strong(580, 278, 230, 56, "Planner agent", "builds the plan")

    g += box(560, 60, 100, 56, "Claude", "on Bedrock")
    g += line(620, 170, 620, 118) + text(626, 148, "model", s, anchor="start")
    g += box(675, 60, 95, 56, "Gateway", "AgentCore")
    g += line(722, 170, 722, 118) + text(728, 148, "tools", s, anchor="start")
    g += line(770, 88, 798, 88) + box(800, 60, 125, 56, "Service graph", "MCP server, Lambda")
    return svg(
        940,
        360,
        g,
        "The user's browser talks to the Next.js frontend on Amplify. The frontend starts jobs and polls "
        "the Api Lambda, which saves each job in a DynamoDB table and starts the Worker Lambda. The Worker "
        "calls the conversation or planner agent on AgentCore Runtime and saves the reply to the job. "
        "The agents call Claude on Bedrock and use the service graph MCP server through AgentCore Gateway",
    )


def journey():
    s = 11
    g = box(10, 70, 110, 64, "User", "describes situation")
    g += line(120, 102, 148, 102)
    g += box(150, 70, 150, 64, "Conversation agent", "gathers context")
    g += line(225, 134, 225, 180, head=False) + line(225, 180, 65, 180, head=False) + line(65, 180, 65, 136)
    g += text(145, 198, "asks the next question, at most 5", s)
    g += line(300, 102, 328, 102)
    g += strong(330, 70, 150, 64, "Situation and facts", "when judged complete")
    g += line(480, 102, 508, 102)
    g += text(495, 160, "user presses", s) + text(495, 174, "Start plan", s)
    g += line(495, 150, 495, 108, head=False, dash="3 3")
    g += box(510, 70, 140, 64, "Planner agent", "builds the plan")
    g += line(650, 102, 678, 102)
    g += box(680, 70, 110, 64, "Plan", "steps and tasks")
    g += box(250, -28, 160, 46, "Claude", "on Bedrock")
    g += box(430, -28, 160, 46, "Service graph", "MCP via Gateway")
    g += line(225, 70, 225, 48, head=False) + line(580, 70, 580, 48, head=False)
    g += line(225, 48, 580, 48, head=False)
    g += line(330, 48, 330, 20) + text(338, 40, "model", s, anchor="start")
    g += line(510, 48, 510, 20) + text(518, 40, "tools", s, anchor="start")
    return svg(
        800,
        248,
        group(0, 38, g),
        "The user describes their situation and the conversation agent asks up to five questions to gather "
        "context. When it judges the conversation complete, it sums up the situation and the facts collected. "
        "When the user presses Start plan, these go to the planner agent, which queries the service graph "
        "and returns a plan of steps and tasks. Both agents call Claude on Bedrock and use the service graph",
    )


def components():
    s = 11
    w = 160
    g = area(10, 10, 190, 330, "Frontend, Next.js")
    g += box(25, 50, w, 56, "Pages and poller", "React, in the browser")
    g += line(105, 106, 105, 158)
    g += box(25, 160, w, 56, "Server actions", "start jobs, /api/job")
    g += line(105, 216, 105, 268)
    g += box(25, 270, w, 56, "Backend client", "invokes Api Lambda")
    g += line(185, 298, 253, 298)

    g += area(240, 10, 200, 330, "Backend, Lambdas")
    g += box(255, 50, 170, 56, "Worker handler", "claims and runs job")
    g += line(355, 106, 355, 158) + text(361, 130, "claims,", s, anchor="start") + text(361, 144, "saves reply", s, anchor="start")
    g += box(285, 160, 140, 56, "Job store", "job records")
    g += line(355, 270, 355, 218) + text(361, 240, "saves job,", s, anchor="start") + text(361, 254, "reads job", s, anchor="start")
    g += box(255, 270, 170, 56, "Api handler", "start, get job")
    g += line(270, 270, 270, 108) + text(276, 248, "starts", s, anchor="start")
    g += line(425, 188, 468, 188) + box(470, 160, 100, 56, "DynamoDB", "jobs table")

    g += line(425, 78, 613, 78) + text(520, 70, "invokes", s)
    g += area(600, 10, 200, 330, "AgentCore Runtime")
    g += strong(615, 50, 170, 56, "Entry point", "main.py, per agent")
    g += line(700, 106, 700, 158)
    g += strong(615, 160, 170, 56, "Chat or plan logic", "builds prompt, shapes reply")
    g += line(700, 216, 700, 268)
    g += strong(615, 270, 170, 56, "Agent runner", "Strands, prompts")

    g += box(825, 50, 120, 56, "Gateway", "AgentCore")
    g += line(945, 78, 983, 78)
    g += area(970, 10, 190, 220, "Service graph, Lambda")
    g += box(985, 50, w, 56, "MCP tools", "five graph tools")
    g += line(1065, 106, 1065, 148)
    g += box(985, 150, w, 56, "Graph engine", "rules and data")
    g += box(825, 270, 120, 56, "Claude", "on Bedrock")
    g += line(785, 312, 823, 312)
    g += line(785, 284, 810, 284, head=False) + line(810, 284, 810, 78, head=False) + line(810, 78, 823, 78)
    return svg(
        1170,
        350,
        g,
        "Inside the frontend, pages and a poller in the browser call server actions, which use a backend "
        "client to invoke the Api Lambda. In the backend, the Api handler saves and reads jobs through the job "
        "store in DynamoDB and starts the Worker handler, which claims the job, invokes the agent and saves the reply. On AgentCore "
        "Runtime, each agent's entry point passes the request to its chat or plan logic and then to an agent "
        "runner, which calls Claude on Bedrock and the service graph's MCP tools through Gateway. The tools "
        "use a graph engine over the rules and data",
    )


def proposed():
    s = 11
    g = box(10, 190, 90, 56, "User")
    g += line(100, 210, 128, 140) + line(100, 226, 128, 296)
    g += box(130, 110, 150, 56, "Web frontend", "Next.js on Amplify")
    g += strong(130, 270, 150, 56, "GOV.UK app", "React Native, new")
    g += line(280, 138, 308, 208) + line(280, 298, 308, 228)

    g += strong(310, 190, 140, 56, "Public API", "new, API Gateway")
    g += strong(310, 40, 140, 52, "Identity provider", "new, signs users in")
    g += line(380, 190, 380, 94) + text(386, 145, "checks token", s, anchor="start")
    g += line(450, 218, 478, 110) + line(450, 218, 491, 421)

    g += area(480, 10, 470, 170, "Chat V2 agent/orchestrator")
    g += text(560, 102, "tbc", 16, 700, MUTED)
    g += box(765, 45, 170, 52, "Conversation agent", "asks the next question")
    g += line(590, 180, 590, 243) + text(598, 199, "on Start plan, sends context", s, anchor="start")

    g += area(480, 210, 240, 252, "Plans backend")
    g += strong(493, 245, 108, 52, "Generate plan", "new endpoint")
    g += line(601, 271, 613, 271)
    g += box(615, 245, 95, 52, "Plan worker", "Lambda")
    g += line(547, 297, 580, 328) + line(662, 297, 630, 328)
    g += strong(550, 330, 110, 50, "Plan store", "new, by user")
    g += line(547, 395, 580, 382)
    g += strong(493, 395, 108, 52, "Get plans", "new endpoint")

    g += line(710, 271, 763, 271)
    g += area(750, 210, 200, 110, "AgentCore Runtime")
    g += box(765, 245, 170, 52, "Planner agent", "builds the plan")

    g += line(935, 71, 975, 71, head=False) + line(935, 271, 975, 271, head=False)
    g += line(975, 71, 975, 271, head=False)
    g += line(975, 136, 998, 136) + box(1000, 110, 110, 52, "Claude", "on Bedrock")
    g += line(975, 226, 998, 226) + box(1000, 200, 110, 52, "Gateway", "AgentCore")
    g += line(1055, 252, 1055, 288) + box(1000, 290, 110, 52, "Service graph", "MCP, Lambda")
    return svg(
        1120,
        472,
        g,
        "Proposed: users reach the service through the web frontend or a new GOV.UK app in React Native. "
        "Both call a new public API, which checks the user's token with an identity provider. The API routes "
        "to two separate parts. A Chat V2 agent or orchestrator holds the conversation agent; how it is "
        "built is to be confirmed. When the user presses Start plan, it sends the context to a new generate "
        "plan endpoint. The plans backend also has a new get plans endpoint, "
        "a plan worker and a new plan store kept by user, and calls the planner agent. Both agents call "
        "Claude on Bedrock, and reach the service graph through AgentCore Gateway",
    )


write(os.path.join(HERE, "containers.svg"), containers())
write(os.path.join(HERE, "proposed.svg"), proposed())
write(os.path.join(HERE, "components.svg"), components())
write(os.path.join(HERE, "journey.svg"), journey())
