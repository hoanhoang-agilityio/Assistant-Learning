# Pydantic data models and specification

Transcribed from the implementation-detail spec (PDF pp. 16–26). Implemented in
`src/schemas/domain/` — `profile.py`, `exercise.py`, `template.py`, `plan.py`,
`verification.py`. The enumerations below live in `src/enums/domain.py`.

## Enumerations

### `Sex` — user biological sex

| Value | Description |
|---|---|
| `MALE` | Male |
| `FEMALE` | Female |

### `ActivityLevel` — daily physical activity level

| Value | Description |
|---|---|
| `SEDENTARY` | Sedentary (desk job, little to no exercise) |
| `LIGHT` | Lightly active (light exercise/sports 1–3 days/week) |
| `MODERATE` | Moderately active (moderate exercise/sports 3–5 days/week) |
| `VERY_ACTIVE` | Very active (hard exercise/sports 6–7 days a week) |
| `EXTRA_ACTIVE` | Extra active (very hard exercise, physical job or training 2x/day) |

### `FitnessGoal` — user fitness goal

| Value | Description |
|---|---|
| `FAT_LOSS` | Fat loss |
| `MUSCLE_GAIN` | Muscle gain / hypertrophy |
| `MAINTENANCE` | Weight/fitness maintenance |
| `STRENGTH` | Strength building |
| `GENERAL_FITNESS` | General fitness and health improvement |

### `BodyRegion` — target body region

| Value | Description |
|---|---|
| `UPPER` | Upper body |
| `LOWER` | Lower body |
| `FULL_BODY` | Full body |
| `CORE` | Core region |

### `MuscleGroup` — specific muscle groups

`CHEST`, `BACK`, `SHOULDERS`, `BICEPS`, `TRICEPS`, `FOREARMS`, `QUADS`, `HAMSTRINGS`, `GLUTES`,
`CALVES`, `ABS`, `LOWER_BACK`, `HIP`

### `MovementPattern` — exercise movement patterns

| Value | Description |
|---|---|
| `HORIZONTAL_PUSH` | Horizontal push (bench press, push-up) |
| `HORIZONTAL_PULL` | Horizontal pull (barbell row, cable row) |
| `VERTICAL_PUSH` | Vertical push (overhead press) |
| `VERTICAL_PULL` | Vertical pull (pull-up, lat pulldown) |
| `SQUAT` | Squat / knee dominant (back squat) |
| `HINGE` | Hinge / hip dominant (deadlift, hip thrust) |
| `LUNGE` | Lunge / single leg (walking lunge) |
| `CARRY` | Carry (farmer's carry) |
| `ISOLATION` | Isolation / single-joint |
| `ROTATION` | Rotational movement |
| `ANTI_ROTATION` | Anti-rotation (Pallof press) |
| `FLEXION` | Flexion |
| `EXTENSION` | Extension |

### `EquipmentType` — available equipment types

`BODYWEIGHT`, `BARBELL`, `DUMBBELL`, `CABLE`, `MACHINE`, `KETTLEBELL`, `RESISTANCE_BAND`,
`SMITH_MACHINE`, `BENCH`, `OTHER`

### `DifficultyLevel` — exercise difficulty level

`BEGINNER`, `INTERMEDIATE`, `ADVANCED`

### `InjuryStatus` — injury status

| Value | Description |
|---|---|
| `ACTIVE` | Active injury / currently causing pain |
| `RECOVERING` | Recovering / in rehabilitation |
| `RESOLVED` | Fully resolved / healed |

### `RestrictionAction` — restriction level for movements/exercises

`PROHIBITED`, `LIMITED`, `ALLOWED`

> Spec note: the PDF's `RestrictionAction` value table duplicates the `InjuryStatus` rows, while the
> `MovementRestriction.action` description names `PROHIBITED / LIMITED / ALLOWED`. The description
> is the intended set and is what gets implemented.

## Data models

### `MovementRestriction`

A movement or exercise pattern that should be avoided or limited because of an injury.

| Field | Type | Description | Required |
|---|---|---|---|
| `movement_pattern` | `MovementPattern` | Affected movement pattern | Yes |
| `action` | `RestrictionAction` | Restriction action level | Yes |
| `reason` | `str` | Reason for the restriction | No |

### `Injury`

User's current or previous injury information.

| Field | Type | Description | Required |
|---|---|---|---|
| `body_part` | `str` | Affected body part, e.g. shoulder, knee, lower_back | Yes |
| `status` | `InjuryStatus` | Injury status | Yes (default `ACTIVE`) |
| `severity` | `str` | Injury severity description | No |
| `restrictions` | `list[MovementRestriction]` | Movement restrictions caused by the injury | Yes (default `[]`) |
| `notes` | `str` | Additional notes on injury | No |

### `UserEquipment`

| Field | Type | Description | Required |
|---|---|---|---|
| `equipment` | `list[EquipmentType]` | Available standard equipment | Yes (default `[]`) |
| `other_equipment` | `list[str]` | Additional/custom equipment | Yes (default `[]`) |

### `UserProfile`

User information used by the coach agent when generating a workout plan.

| Field | Type | Description | Required |
|---|---|---|---|
| `age` | `int` | Age in years (13–100) | Yes |
| `sex` | `Sex` | Biological sex | Yes |
| `height_cm` | `float` | Height in centimeters (> 0) | Yes |
| `current_weight_kg` | `float` | Current body weight in kilograms (> 0) | Yes |
| `target_weight_kg` | `float` | Target body weight in kilograms (> 0) | No |
| `activity_level` | `ActivityLevel` | Daily activity level | Yes |
| `goal` | `FitnessGoal` | Primary fitness goal | Yes |
| `training_days_per_week` | `int` | Training days per week (1–7) | Yes |
| `injuries` | `list[Injury]` | Current or relevant previous injuries | Yes (default `[]`) |
| `available_equipment` | `UserEquipment` | Equipment available to the user | Yes (default `UserEquipment()`) |
| `preferences` | `list[str]` | Optional user preferences, e.g. prefers dumbbells | Yes (default `[]`) |
| `notes` | `str` | Additional user notes | No |

### `ExerciseContraindication`

An injury/body-part condition under which an exercise should not be selected.

| Field | Type | Description | Required |
|---|---|---|---|
| `body_part` | `str` | Affected body part | Yes |
| `movement_patterns` | `list[MovementPattern]` | Contraindicated movement patterns | Yes (default `[]`) |
| `reason` | `str` | Reason for contraindication | No |

### `ExerciseMuscleTarget`

| Field | Type | Description | Required |
|---|---|---|---|
| `muscle` | `MuscleGroup` | Target muscle group | Yes |
| `priority` | `str` | Muscle involvement role (`primary` or `secondary`) | Yes |

> **Deviation (03/09).** Not implemented, and removed from `src/schemas/domain/exercise.py`.
> `Exercise` carries `primary_muscles` and `secondary_muscles` as two plain lists, which
> encodes the same priority in the field name, so nothing ever constructed this model.

### `Exercise`

Structured exercise definition available to the coach agent.

| Field | Type | Description | Required |
|---|---|---|---|
| `id` | `str` | Unique exercise identifier | Yes |
| `name` | `str` | Exercise name | Yes |
| `description` | `str` | Detailed exercise description | No |
| `body_region` | `BodyRegion` | Primary body region targeted | Yes |
| `primary_muscles` | `list[MuscleGroup]` | Primary target muscles | Yes (min items 1) |
| `secondary_muscles` | `list[MuscleGroup]` | Secondary target muscles | Yes (default `[]`) |
| `movement_pattern` | `MovementPattern` | Primary movement pattern | Yes |
| `equipment` | `list[EquipmentType]` | Required equipment | Yes (default `[]`) |
| `difficulty` | `DifficultyLevel` | Exercise difficulty level | Yes |
| `contraindications` | `list[ExerciseContraindication]` | Injury contraindications | Yes (default `[]`) |
| `instructions` | `list[str]` | Step-by-step instructions | No |
| `notes` | `str` | Additional notes | No |

### `ExerciseSlot`

A slot in the workout template that the coach agent needs to fill with an exercise.

| Field | Type | Description | Required |
|---|---|---|---|
| `slot_id` | `str` | Identifier for the exercise slot | Yes |
| `exercise_type` | `str` | Desired exercise type description | No |
| `target_muscles` | `list[MuscleGroup]` | Target muscle groups for this slot | Yes (default `[]`) |
| `allowed_movement_patterns` | `list[MovementPattern]` | Allowed movement patterns | Yes (default `[]`) |
| `excluded_movement_patterns` | `list[MovementPattern]` | Excluded movement patterns | Yes (default `[]`) |
| `required_body_region` | `BodyRegion` | Required body region constraint | No |
| `alternatives_allowed` | `bool` | Whether alternative exercises are allowed | Yes (default `True`) |
| `notes` | `str` | Slot specific notes | No |

### `WorkoutDayTemplate`

Structure and constraints of one training day.

| Field | Type | Description | Required |
|---|---|---|---|
| `day_number` | `int` | Day sequence number (>= 1) | Yes |
| `name` | `str` | Workout day name (e.g. Leg Day, Upper Push) | Yes |
| `body_region` | `BodyRegion` | Primary body region for the day | Yes |
| `target_muscles` | `list[MuscleGroup]` | Target muscle groups for the day | Yes (default `[]`) |
| `exercise_slots` | `list[ExerciseSlot]` | Exercise slots | Yes (min items 1) |
| `notes` | `str` | Notes for the training day | No |

### `WorkoutTemplate`

Overall workout plan template defining structure for the coach agent to select actual exercises.

| Field | Type | Description | Required |
|---|---|---|---|
| `id` | `str` | Unique template identifier | Yes |
| `name` | `str` | Template name | Yes |
| `description` | `str` | General template description | No |
| `training_days` | `list[WorkoutDayTemplate]` | Training days | Yes (min items 1) |
| `notes` | `str` | Overall template notes | No |

## The plan the coach agent returns

Not in the PDF: the spec names the coach agent's output as "training plan — goal, calories,
macro, training days, exercises" without a model. These are that model, in
`src/schemas/domain/plan.py`.

A prescription references a slot and a catalogue row **by id and nothing else**. Carrying the
exercise name or its equipment as well would let the agent state one thing while
`exercise_id` points at another, which is the hallucination the slot/exercise split exists to
close. Anything a reader needs is resolved from the catalogue at render time.

### `MacroTargets`

| Field | Type | Description | Required |
|---|---|---|---|
| `protein_g` | `float` | Daily protein target in grams (>= 0) | Yes |
| `carbs_g` | `float` | Daily carbohydrate target in grams (>= 0) | Yes |
| `fat_g` | `float` | Daily fat target in grams (>= 0) | Yes |

`MacroTargets.calories` returns what the three come to at 4/4/9 kcal per gram — the macro
consistency check compares it against `TrainingPlan.daily_calories`.

### `NutritionTargets`

What `calc_macro` returns: the plan's calorie and macro fields plus the working behind them.

| Field | Type | Description | Required |
|---|---|---|---|
| `goal` | `FitnessGoal` | The goal these targets were computed for | Yes |
| `bmr` | `int` | Basal metabolic rate in kcal/day (> 0) | Yes |
| `tdee` | `int` | Maintenance calories in kcal/day (> 0) | Yes |
| `daily_calories` | `int` | Daily calorie target (> 0) | Yes |
| `macros` | `MacroTargets` | Daily macro targets | Yes |

`daily_calories` is what `macros` come to at 4/4/9 rather than the raw goal-adjusted figure,
so a plan that copies both passes the macro consistency check as it stands.

### `PlannedExercise`

| Field | Type | Description | Required |
|---|---|---|---|
| `slot_id` | `str` | The template slot this exercise fills | Yes |
| `exercise_id` | `str` | Id of an exercise the catalogue returned | Yes |
| `sets` | `int` | Number of working sets (> 0) | Yes |
| `reps` | `str` | Repetitions per set, e.g. `8-12` | Yes |
| `rest_seconds` | `int` | Rest between sets (>= 0) | No |
| `notes` | `str` | Coaching notes | No |

### `PlanDay`

| Field | Type | Description | Required |
|---|---|---|---|
| `day_number` | `int` | Day sequence number (>= 1) | Yes |
| `name` | `str` | Day name | Yes |
| `exercises` | `list[PlannedExercise]` | Prescriptions for the day | Yes (min items 1) |
| `body_region` | `BodyRegion` | Primary region trained | No |
| `notes` | `str` | Notes for the day | No |

### `TrainingPlan`

| Field | Type | Description | Required |
|---|---|---|---|
| `template_id` | `str` | Template the plan was built from | Yes |
| `goal` | `FitnessGoal` | The goal this plan serves | Yes |
| `daily_calories` | `int` | Daily calorie target (> 0) | Yes |
| `macros` | `MacroTargets` | Daily macro targets | Yes |
| `training_days` | `list[PlanDay]` | The training week, in order | Yes (min items 1) |
| `summary` | `str` | Short description for the user | No |
| `notes` | `str` | Overall notes | No |

`template_id` plus `slot_id` are what make deterministic verification possible: the gate
re-resolves the template by id and can then check that every slot was filled exactly once,
and that each chosen exercise actually satisfies the slot it was chosen for.

## Where the catalogue lives

`Exercise` and `WorkoutTemplate` are stored in Postgres, in the Alembic-owned `exercise` and
`workout_template` tables (`src/models/catalogue.py`). Exercises keep their filterable
attributes as real columns because `load_exercise` queries on them; a template's days and
slots are one JSONB document, because nothing queries a slot independently of the template
it belongs to.

The seed in `data/` is converted from this project's own copy of the source catalogue in
`data/source/` by `scripts/convert_catalogue_seed.py`, which holds every mapping decision.
The source originated in `subagents-architecture` and is kept here so each project seeds
from its own data. Three additions to the spec's enums were needed for the conversion to
stay lossless:

| Enum | Added | Why |
|---|---|---|
| `MovementPattern` | 18 single-joint and trunk patterns | The slot filter is only as precise as this enum. Collapsed into `ISOLATION`, a biceps slot and a calf slot become the same query, and `ABDUCTION` and `REAR_DELT_PULL` — separate slots in the 5-day template — become indistinguishable. |
| `MuscleGroup` | `LATS`, `FRONT_DELTS`, `SIDE_DELTS`, `REAR_DELTS`, `OBLIQUES` | The catalogue distinguishes the deltoid heads; `SHOULDERS` alone cannot tell a rear-delt row from a lateral raise. |
| `EquipmentType` | `PULL_UP_BAR`, `DIP_STATION` | Mapping them to `OTHER` would make the availability check ask a user whether they own "other". |

`WorkoutTemplate` also gained `goals` and `popularity` — `load_template` selects on the
user's goal, and the spec's template model had no goal field — and `ExerciseSlot` gained
`sets`, `rep_range` and `rir_range`, which the seed templates prescribe and which give the
training-volume check something to verify against.

Every exercise is prescribed in sets and repetitions. The source carried four rows measured
in time — three planks and a dead bug — and a timed row gives the coach agent nothing to
put in `reps`, so it wrote `"45-60s"` and the volume check failed the plan on every retry.
They are re-expressed as repetition movements in `data/source/exercise_seed.json`, and
`convert_catalogue_seed.py` now refuses a source row carrying `unit` or `duration_seconds`
rather than dropping the field silently.
