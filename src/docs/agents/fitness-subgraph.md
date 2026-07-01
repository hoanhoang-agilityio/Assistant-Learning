# Fitness Subgraph — Architecture (Hybrid Deterministic + LLM Planner)

> **Status:** Architecture reference  
> **Scope:** `src/core/subgraphs/fitness/` — macro calculation, LLM workout planning, safety validation  
> **Date:** 2026-07-01

**Related:** [Workflow](./workflow.md) · [Supervisor](./supervisor.md) · [Planning](./planning-subgraph.md) · [Research](./research-subgraph.md)

---

## Executive Summary

The Fitness subgraph combines **deterministic macro calculation** with an **LLM Fitness Planner** (STANDARD tier) that produces a structured workout plan. A **safety validation loop** can retry the planner up to 3 times when deterministic checks fail.

The subgraph loads upstream context from VFS (profile, execution plan, research findings, verification feedback), writes artifacts to `fitness/`, and always routes to **Verification** (not back to Supervisor) after completion.

---

## 1. Graph Architecture

### 1.1 Nodes

| Node | Responsibility |
|------|----------------|
| `load_context` | Load profile, execution plan, research findings, verification feedback from VFS |
| `calculate_macros` | Deterministic BMR/TDEE/macro targets and training constraints |
| `fitness_planner` | LLM structured workout generation via `generate_structured_workout()` |
| `safety_check` | Deterministic validation of macros + structured workout |
| `synthesize_plan` | Render markdown draft plan from macros + structured workout |
| `write_artifacts` | Persist workout, calculations, safety flags, and final plan to VFS |

### 1.2 Execution Flow

```mermaid
flowchart TD
    START((START)) --> load_context
    load_context --> calculate_macros
    calculate_macros --> fitness_planner
    fitness_planner --> safety_check
    safety_check -->|passed| synthesize_plan
    safety_check -->|failed, attempts < 3| fitness_planner
    safety_check -->|failed, attempts >= 3| synthesize_plan
    synthesize_plan --> write_artifacts
    write_artifacts --> END((END))
```

`MAX_PLANNER_ATTEMPTS = 3`. After max attempts, synthesis proceeds with safety warnings embedded in the draft plan.

### 1.3 State (`FitnessState`)

| Field | Set by |
|-------|--------|
| `profile`, `execution_plan`, `structured_findings`, `evidence_summary`, `verification_feedback` | `load_context` |
| `macro_targets`, `training_constraints` | `calculate_macros` |
| `structured_workout`, `planner_attempts` | `fitness_planner` |
| `safety_result`, `planner_feedback` (on retry) | `safety_check` |
| `draft_plan` | `synthesize_plan` |
| VFS artifacts | `write_artifacts` |

---

## 2. Context Loading

`load_fitness_context()` in [`utils.py`](../../core/subgraphs/fitness/utils.py) reads:

| VFS path | Usage |
|----------|-------|
| `plan/profile.json` | User profile |
| `plan/execution_plan.json` | Research task alignment for planner |
| `research/findings.json` | `structured_findings` (preferred) or `evidence_summary` |
| `verify/verification_v1.json` | `verification_feedback` from prior verification run |

When `structured_findings.consensus` is present, a formatted evidence summary is derived for the markdown draft.

---

## 3. Deterministic Macro Calculation

`calculate_macros_data()` — no LLM involved.

| Step | Method |
|------|--------|
| BMR | Mifflin-St Jeor (sex-adjusted) |
| TDEE | BMR × activity multiplier |
| Calories | Goal adjustment (fat loss −500, muscle gain +300, strength +200) |
| Floor/ceiling | Min 1200 (F) / 1500 (M) kcal; max 4500 kcal |
| Protein | 1.8–2.4 g/kg by goal and `high_protein` constraint |
| Fat / carbs | 25% fat calories; remainder to carbs |

**Training constraints** derived alongside macros:

- `days_per_week` — from profile, constraints, or activity level pattern
- `session_duration_minutes` — from constraints (default 60)
- `equipment` — `gym` | `home` | `bodyweight`
- `goal` — from profile

---

## 4. LLM Fitness Planner

Implementation: [`planner.py`](../../core/subgraphs/fitness/planner.py)

| Aspect | Detail |
|--------|--------|
| Model tier | STANDARD (`invoke_standard_structured_output`) |
| Output schema | `StructuredWorkout` — [`schema.py`](../../core/subgraphs/fitness/schema.py) |
| System prompt | [`prompts.py`](../../core/subgraphs/fitness/prompts.py) |
| Test override | `configure_fitness_planner(override)` |

### 4.1 Planner Input Payload

`build_planner_payload()` sends JSON with:

- `profile`, `constraints`
- `macro_targets`, `training_constraints` (engine-computed — planner must not recalculate)
- `execution_plan` (tasks + rationale from Planning stage)
- `structured_findings` (from Research)
- `planner_feedback` (from failed safety checks)
- `verification_feedback` (from prior Verification run)

### 4.2 StructuredWorkout Schema

```python
StructuredWorkout:
  split: str
  goal: str
  days: list[WorkoutDay]       # 1–6 days
  weekly_sets: int             # Must equal sum of all exercise sets
  progression: str | None
  substitutions: list[str]
  notes: list[str]
  evidence_applied: list[str]

WorkoutDay:
  name, focus, exercises: list[WorkoutExercise]

WorkoutExercise:
  name, sets (1–10), reps, notes?
```

### 4.3 Planner Rules (highlights)

- Obey `training_constraints.days_per_week` exactly
- Obey `training_constraints.equipment` — no gym machines for bodyweight/home
- Never output calorie, macro, BMR, or TDEE values
- Populate `evidence_applied` with specific research influences
- Address all `planner_feedback` and `verification_feedback` on retry

---

## 5. Safety Validation Loop

`validate_workout_safety_data()` — deterministic, no LLM.

### 5.1 Macro Checks

| Flag | Condition |
|------|-----------|
| `calories_below_safe_minimum` | Below sex-based floor |
| `calories_above_recommended_maximum` | Above 4500 kcal |
| `aggressive_calorie_deficit` | Below 75% of TDEE |
| `protein_intake_too_high` | Above 3.0 g/kg |

### 5.2 Workout Checks

| Flag | Condition |
|------|-----------|
| `training_day_count_mismatch` | Days ≠ `days_per_week` |
| `training_frequency_too_high` | More than 6 training days |
| `weekly_sets_mismatch` | Declared ≠ computed sum |
| `weekly_training_volume_too_high` | Weekly sets > 120 |
| `invalid_set_count` | Sets outside 1–10 per exercise |
| `duplicate_exercise` | Same exercise twice in one day |
| `equipment_mismatch` | Exercise incompatible with equipment setting |
| `empty_exercises` | Day has no exercises |
| `invalid_workout_schema` | Pydantic validation failure |

On failure with attempts remaining, safety feedback is merged into `planner_feedback` and the planner re-runs.

---

## 6. Plan Synthesis & VFS Artifacts

### 6.1 Draft Plan

`synthesize_plan_data()` renders markdown including macro targets, training plan, progression, evidence applied, verification feedback, and safety warnings.

### 6.2 VFS Writes

`write_fitness_artifacts()` persists:

| Path | Content |
|------|---------|
| `fitness/workout.json` | Full `StructuredWorkout` JSON |
| `fitness/calculations.json` | `macro_targets` + `workout_summary` |
| `fitness/safety_flags.json` | List of safety feedback strings |
| `fitness/final_plan.md` | Markdown draft plan |

---

## 7. Orchestration Integration

`invoke_fitness_subgraph()` returns `{ "current_node": "fitness" }`. Main graph routes `fitness → verification` directly.

On verification failure, Supervisor may route `FIX_REASONING` back to Fitness; planner reloads `verify/verification_v1.json` feedback from VFS on next run.

---

## 8. Module Layout

```
src/core/subgraphs/fitness/
├── schema.py           # StructuredWorkout, SafetyResult
├── prompts.py          # Fitness planner system prompt
├── planner.py          # LLM agent + configure override
├── graph.py            # LangGraph (6 nodes + retry loop)
├── state.py            # FitnessState
├── utils.py            # Macros, safety, VFS, synthesis
├── tools.py            # LangChain tool wrappers
└── agent.py            # Facade for orchestration
```

---

## 9. Downstream Consumers

| Consumer | Reads |
|----------|-------|
| Verification | `fitness/final_plan.md`, `fitness/workout.json`, `fitness/calculations.json` |
| Persist | `fitness/final_plan.md` → `final/final_plan.md` |
| Fitness (rerun) | `verify/verification_v1.json` on `FIX_REASONING` loop |

---

## 10. Key File Reference

| File | Role |
|------|------|
| `planner.py` | Core LLM fitness planner |
| `graph.py` | Subgraph wiring + safety retry loop |
| `utils.py` | Macro math, safety rules, VFS I/O |
| `tests/helpers/fitness.py` | Deterministic planner override |
