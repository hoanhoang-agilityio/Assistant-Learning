Extract training-profile facts the user has stated.

# Rules

- **Only extract what was actually said.** Leave a field `null` if the user did
  not state it. A guess here becomes a calorie target or an exercise filter, and
  a wrong one is invisible — it looks exactly like a correct one.
- Do not carry forward or restate what is already known; return only what this
  conversation tells you.
- **Take facts only from what the *user* said.** The conversation below includes
  the assistant's turns. Those are suggestions and summaries, not statements
  about the user: an assistant sentence saying "your plan avoids overhead
  pressing" is not the user saying they avoid it. Extracting from the
  assistant's own output is how a memory store fills up with its own echo.
- If the user corrects something ("actually I'm 73 now"), return the new value.
- Convert units to kilograms and centimetres. `165 lbs` → `74.8`, `5'10"` → `178`.

# Controlled vocabularies

Return **exactly** one of these tokens, or `null`. Anything else is discarded.

- `sex`: `male`, `female`
- `activity_level` — their life *outside* training, since training is counted
  separately: `sedentary` (desk job, little walking), `light`, `moderate`,
  `active`, `very_active` (physical job)
- `goal`: `fat_loss`, `muscle_gain`, `recomp`, `general_health`
- `injuries`: `knee_pain_patellofemoral`, `shoulder_impingement`.
  Return `[]` when the user says they have none. Leave `null` if they have not
  said either way. If they describe an injury that is **not** in this list, set
  `injuries: []` and put their exact words in `unmapped_injury` — a wrong
  mapping is worse than no mapping, because the wrong contraindications get
  applied and the real problem does not. Recording it verbatim means the system
  can tell them plainly that nothing screens for it.
- `equipment`: `barbell`, `dumbbell`, `cable`, `machine`, `smith_machine`,
  `kettlebell`, `resistance_band`, `bodyweight`, `pull_up_bar`, `dip_station`.
  "Full gym" or "commercial gym" means all of them. "Home gym" means only what
  they name.
- `level`: 1 for a beginner, 3 for a couple of years of consistent training, 5
  for advanced. Infer only from an explicit statement about experience.

# `preferences`

Free text, and the one field that is a *list*: what the user likes doing and what
they want to avoid. "Hates burpees", "prefers dumbbells over machines", "can only
train mornings".

Return **only what was stated in the latest turn**, and nothing else. This field
accumulates — earlier preferences are already held and will be joined to yours by
the code, not by you. Repeating them back is how the list drifts away from what
the user actually said, one rewording at a time.

Several at once are separated with `;`. Leave it `null` when the latest turn
states none, which is most turns.

Not preferences: an injury (that is `injuries` or `unmapped_injury`), a goal, or
an equipment list. Nor anything the assistant proposed and the user did not
answer.

# Conversation

{conversation}
