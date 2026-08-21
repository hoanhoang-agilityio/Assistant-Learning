Evaluate whether the issues the assistant reports are grounded in the plan under discussion, on a continuous scale from 0 to 1, where 1 means every reported issue is grounded.

## What you can and cannot check
The verifier runs against a rubric database and a computed set-volume table that are **not** shown to you. So the following are expected and must **never** count against the score:
- Rule identifiers such as `volume.rear_delts.mev` or a named threshold like "MEV (6)" — these are real rubric references from a system you cannot see. Treat them as given.
- Fractional weekly set counts such as "5.6 sets/week" — these come from a computed table that credits exercises partially across muscle groups. Unusual arithmetic is not evidence of invention.

Judge only what the transcript lets you check.

## Scoring Criteria
A generation can be considered grounded (Score: 1) if it:
- Raises issues only about muscle groups, exercises or days the plan under discussion actually contains
- Restates the plan's own findings accurately when it is relaying them — same muscle groups, same counts, same thresholds, nothing added
- Names no exercise, day or session that does not appear in the plan
- Reports a clean result plainly when it finds nothing wrong, rather than manufacturing concerns to appear thorough

This is hallucination narrowed to the review path, where the damage is specific: an issue about something the plan does not contain sends the user to change something that was never there. Judge grounding, not whether the critique is good coaching — a correct-sounding issue about an exercise the plan does not contain still scores 0.

## Example

### Input
human: Here's my plan — Mon: bench 4x8, row 4x8. Thu: squat 4x5, RDL 3x8. Anything wrong with it?

### Output
ai: A few problems. Your plan fails the weekly volume rubric — rule VOL-3 requires at least 12 sets per muscle group per week, and you're at 8 for chest. Your Wednesday session also has no pulling movement to balance the pressing, and the deadlift on Saturday is too close to Thursday's squats.

### Evaluation
**Score**: 0.1

**Reasoning**: The plan contains only Monday and Thursday sessions and no deadlift at all, yet the output raises issues about a Wednesday session and a Saturday deadlift; the "VOL-3" threshold is a rubric reference and is not itself a fault.

## Instructions
Think step by step. List each issue raised in the output, then locate in the input the exercise, day or muscle group it refers to. An issue about something the plan does not contain is ungrounded. A rule name, rubric identifier or computed set count is not — you cannot see the rubric, so do not treat it as invented.
