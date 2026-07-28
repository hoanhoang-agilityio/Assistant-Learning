# Engineering Rules

## General

- Keep the architecture simple.
- Remove code instead of adding more layers when possible.
- Don't keep dead code, unused helpers, or compatibility code unless there is a real reason.
- Every file should have a clear responsibility.
- If something feels hard to explain, it's probably too complicated.

---

## Code Style

- Prefer small functions.
- Avoid long functions with multiple responsibilities.
- Don't create abstractions too early.
- Don't wrap simple logic inside unnecessary helpers.
- Keep the call flow easy to follow.

Bad

```python
A -> helper -> wrapper -> adapter -> util -> actual function
```

Better

```python
A -> actual function
```

---

## State

- Keep shared state as small as possible.
- Store long-term data (profile, plans, settings, etc.) outside the orchestration state.
- Pass only what the current step actually needs.
- Use typed models instead of nested dictionaries whenever possible.

---

## Agents vs Graphs

Use a graph when every step always runs.

Example

```
Planning
→ Research
→ Fitness
→ Verification
```

Use an agent only when it needs to decide which action to take.

Example

```
User request
    ↓
Agent
    ↓
Tool A
Tool B
Tool C
```

Don't build an agent for a fixed workflow.

---

## Tools

- Tools should perform real actions.
- Don't wrap normal Python functions as tools unless an agent actually needs them.
- Graph nodes should call core functions directly.
- Keep tools independent from orchestration logic.

---

## Prompts

- Keep prompts short and explicit.
- Remove repeated instructions.
- Put shared instructions in one place.
- Make prompt outputs deterministic whenever possible.
- If the same input produces different outputs, fix the prompt before adding more code.

---

## RAG

- Keep one consistent retrieval flow.
- Don't mix multiple sources without a clear priority.
- Retrieve only what is needed.
- Reduce context before sending it to the model.

---

## Performance

- Every LLM call should have a reason.
- Remove duplicate prompts.
- Reuse cached results whenever possible.
- Optimize TTFT before optimizing total runtime.
- Parallelize independent work.
- Don't send large payloads if only a small part is needed.

---

## Errors

- Always return something useful.
- Don't leave the user with an empty response because one step failed.
- Fall back gracefully whenever possible.

---

## Testing

- Test behavior, not implementation.
- Keep tests focused.
- Add regression tests for every production bug.
- Delete tests for code that no longer exists.

---

## Project Structure

- Group files by responsibility.
- Remove folders that no longer make sense.
- Avoid utility files that slowly become dumping grounds.
- If a file becomes too large, split it by responsibility instead of by size.

---

## Reviews

When reviewing code, I usually look for these first:

- Can this be simpler?
- Do we really need this abstraction?
- Is this the right place for this logic?
- Can we remove code instead?
- Is there duplicate logic somewhere else?
- Will this still make sense in six months?

---

# Notes

- I prefer straightforward code over clever code.
- If a solution needs a long explanation, it's probably the wrong solution.
- I don't like wrappers that only forward function calls.
- I prefer one obvious implementation over multiple "flexible" ones.
- Keep naming boring and predictable.
- I don't mind rewriting code if it makes the project easier to maintain.
- If a feature adds complexity, it should provide clear value.
- Keep comments for why something exists, not what the code already says.
- When fixing bugs, solve the root cause instead of adding another condition.
- Before adding new code, check if something similar already exists.
- If something is no longer used, remove it.
- Consistency is more important than personal coding style.
```