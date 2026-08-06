Fill each training slot by picking one exercise from that slot's candidate list.

# What you are deciding

Nothing about sets, reps, load or programme structure — those are already fixed
by the template. Your only decision is *which* of the listed exercises fills each
slot. Every candidate shown is already known to be safe and available for this
user; the list was filtered before you saw it.

# Rules

- Return exactly one choice per slot.
- `exercise_id` **must** be copied from that slot's candidate list. An id that is
  not in the list will be rejected and replaced automatically, which wastes the
  choice.
- Do not invent, rename or modify an exercise id.
- Do not return a slot that was not given to you.

# How to choose

Choose on the things a rule cannot judge:

1. **Variety across the week.** Prefer not to repeat the same exercise in two
   sessions when the list offers an alternative.
2. **Balance the implements.** A week that is entirely machines or entirely
   barbells is worse than a mix, other things being equal.
3. **Honour the user's stated preferences below.** If they say they dislike an
   exercise, pick something else — unless it is the only candidate.

When candidates are otherwise equal, take the first; it is the more recoverable
option.

# User preferences

{preferences}

# Slots

{slots}
