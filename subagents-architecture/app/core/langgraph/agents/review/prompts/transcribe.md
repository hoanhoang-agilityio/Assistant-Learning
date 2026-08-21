Read the training plan below and write down exactly what it says. You are
transcribing, not interpreting: every judgement about what an exercise is, and
whether the plan is any good, is made after you by code that needs your reading
to be faithful.

# Rules

- **Names are verbatim.** Copy each exercise name exactly as it is written. Do
  not correct spelling, expand abbreviations, resolve "db" to "dumbbell", or
  replace a name with the one you think was meant. "Bench Press" is transcribed
  as "Bench Press", never as "Barbell Bench Press".
- **Never invent a prescription.** If a line gives no sets, `sets` is null. If it
  gives no reps, both `reps_min` and `reps_max` are null. A typical value is
  still an invented one, and it becomes real volume in a real assessment.
- **A fixed count is a range of one value.** "4x8" is `sets: 4, reps_min: 8,
  reps_max: 8`.
- **Split what is written on one line.** "Day 1 — Upper: Bench Press 4x6-8,
  Barbell Row 4x8-10" is one day with two exercises, not one exercise.
- **Keep the user's day labels**, and number the days in the order they appear.
  A plan with no labels still has days: number them and leave the name empty.
- **Take only what is a plan.** Ignore the questions and remarks around it. If
  the message contains no plan at all, return no days rather than inventing one.

# The message

{pasted}
