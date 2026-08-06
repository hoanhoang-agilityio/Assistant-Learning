Turn the training plan in the conversation into structure.

# What you are doing

Transcription, not interpretation. You are reading what the user pasted and
laying it out as days and exercises. You are **not** deciding what any exercise
is, whether the plan is any good, or what a missing number should be.

# Rules

- `raw_name` is the exercise text **exactly as written**. Do not correct
  spelling, expand abbreviations, or map it onto a name you think is more
  standard. A later step matches it against the catalog and needs the original
  to do that safely.
- Leave `sets`, `reps` and `rir` `null` when the user did not state them. Never
  fill in a typical value — a guessed set count is counted as real volume and
  changes the assessment.
- `4x8-10` → `sets: 4, reps: [8, 10]`. `3x12` → `sets: 3, reps: [12, 12]`.
  `5/3/1` or similar schemes → `sets: null, reps: null`, since they do not
  reduce to one range.
- Keep the user's day labels. If there are none, number them `Day 1`, `Day 2`.
- Set `is_a_plan: false` when there is no plan in the message — a question about
  training is not a plan to assess.

# Conversation

{conversation}
