Work out which saved version of the plan the user is asking to go back to.

# Rules

- Return the `version_id` **exactly** as it appears in the list. Do not
  reformat, shorten or invent one.
- Return `null` when you are not confident. The user is then shown the list and
  asked to pick, which costs one extra turn. Restoring the wrong plan costs them
  the plan they are on — so when in doubt, return `null`.
- "The original", "the first one", "how it was at the start" → the **oldest**
  version in the list.
- "The previous one", "what I had before", "undo that" → the version immediately
  before the current one.
- A phrase describing content ("the 5-day one", "the version without deadlifts")
  → match it against the labels. If two versions could match, return `null`.

# Versions

Newest first. The first entry is the plan the user has right now.

{versions}

# What the user said

{query}
