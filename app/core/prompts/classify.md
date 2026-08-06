Classify the user's latest message into exactly one intent.

# Intents

- `build_plan` — wants a new training plan created.
- `change_plan` — wants the plan they already have modified (more days, swap an
  exercise, adjust calories). Put the requested delta in `changes`, e.g.
  `{{"days": 5}}`.
- `check` — pasted or referenced a plan and wants it assessed. This includes
  "is this okay", "what do you think of this", "rate my split".
- `revert` — wants to go back to an earlier version of their plan.
- `general_qa` — a knowledge question with no plan to create, change or assess.

# Scope

`scope` selects which verifiers run. Set it only for `check`:

- mention of nutrition, calories, protein, macros → include `macro`
- mention of volume, sets, frequency, "too much"/"too little" → include `volume`
- mention of pain, injury, or a named joint → include `injury`
- unspecified or general ("is this good?") → all three

Leave `scope` empty for every other intent; the graph sets it from the pipeline.

# Rules

- One intent. When a message could be two, pick the one that describes the
  action the user wants taken, not the topic they mention.
- A question *about* an existing plan that asks for no change is `check`, not
  `change_plan`.
- `changes` is empty unless the intent is `change_plan`.

# Conversation

{conversation}
