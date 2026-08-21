Evaluate whether the macro and calorie numbers presented agree with each other and with the rest of the conversation, on a continuous scale from 0 to 1, where 1 means fully consistent.

## Scoring Criteria
A generation can be considered consistent (Score: 1) if it:
- Has totals that match their components — protein, carbs and fat at 4/4/9 kcal per gram add up to the stated calorie target, within rounding
- Does not contradict figures given earlier in the same conversation without saying what changed and why
- Restates macros that reflect the plan currently under discussion, not a superseded version of it
- Keeps per-day, per-meal and weekly figures in proportion when it presents more than one of them

This is the narration-side mirror of the macro verifier: the computed state can be correct while the text shown to the user drifts from it. Judge only the numbers as written in the transcript. Do not recompute what the user's targets *should* be — a target you disagree with is not an inconsistency.

## Example

### Input
human: I'm 82kg, cutting. What should my macros be?
ai: Let's target 2,100 kcal: 180g protein, 210g carbs, 60g fat.
human: Can you bump the protein a bit?

### Output
ai: Done — protein up to 200g. Your macros are now 200g protein, 210g carbs, 60g fat, still 2,100 kcal per day.

### Evaluation
**Score**: 0.2

**Reasoning**: Adding 20g of protein adds 80 kcal, so the stated total should have moved to roughly 2,180 kcal or another macro should have been reduced to hold 2,100, but the output keeps every other figure and the total unchanged.

## Instructions
Think step by step. Extract every number in the output, check the arithmetic between them, then check them against the numbers earlier in the input.
