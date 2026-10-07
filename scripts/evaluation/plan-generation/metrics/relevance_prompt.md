# Plan relevance judge

You are assessing whether the steps a plan-generation service returned are
relevant to a specific person's situation. You are judging relevance
independently — you are NOT checking the plan against any official
checklist, spine, or step-by-step guide. Judge only against the person's
own situation and context below.

## Person's situation

Situation: {situation}
Context (their own answers, as given to the plan generator): {context}

## What to do

You will be given a numbered list of tasks taken from the plan this person
was shown. For EACH task, decide whether it is relevant to this specific
person's actual, current needs.

Classify every task into exactly one of three verdicts:

- "relevant" — the task addresses a genuine, current need for this person,
  given their situation.
- "premature" — the task addresses a genuine need this person will
  eventually have, but does not have yet. This includes tasks that require
  completing an earlier step the person has not yet reached — they will
  need it once they get there, but not right now. Right topic, wrong timing.
- "irrelevant" — the task does not correspond to any need this person
  actually has, given their situation. Wrong topic entirely.

When you are genuinely uncertain between premature and irrelevant, prefer
premature. When uncertain between relevant and premature, prefer relevant.

Give a one-sentence rationale for each verdict, written plainly enough that
someone auditing the judgement later can see why you decided what you did.

Do not judge tasks against completeness (whether something is missing) —
only judge the tasks you are given. Do not reward or penalise wording,
tone, or presentation. Judge only whether the task's subject matter matches
a need this person has.

## Tasks

{tasks}

## Output format

Respond with ONLY a JSON array — no other text, no markdown code fences,
no commentary before or after. One object per task, in the same order as
given, using exactly this shape:

[
  {{"index": 0, "verdict": "relevant", "rationale": "one sentence"}},
  {{"index": 1, "verdict": "premature", "rationale": "one sentence"}}
]

The array must contain exactly as many objects as there are tasks, in the
same order, each "index" matching the task's number in the list above.
