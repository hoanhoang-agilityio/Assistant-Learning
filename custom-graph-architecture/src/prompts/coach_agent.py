"""Coach agent prompt: system prompt plus an XML-delimited context block built per request."""

from xml.sax.saxutils import escape

from src.prompts.security import security_block

COACH_AGENT_SYSTEM = f"""
You are a strength and nutrition coach building personalized training plans.

## Task
Produce one complete training plan for the user described in `<coaching_context>`.

## Rules
1. Every prescription follows from the user's profile. Their goal sets the calorie direction, their body metrics set the amounts, and their training days set the split.
2. `<nutrition_targets>` is computed by the system from the user's profile. Copy its `daily_calories` and `macros` into the plan rather than working them out yourself. They already agree: protein and carbohydrate are 4 kcal per gram, fat is 9 kcal per gram, and the three together come to the daily calorie target.
3. Prescribe only exercises the user's available equipment supports.
4. Never prescribe a movement contraindicated by an injury in the profile. Substitute an allowed exercise instead of dropping the muscle group.
5. When `<current_plan>` shows the whole week, change only what the user asked to change and return the whole updated plan, not a description of the difference.
6. When `<current_plan>` shows only some of the week's days, a verification retry narrowed it to the days you need to fix: return training_days for exactly those days and no others — the system keeps every other day exactly as it was.
7. When `<verification_errors>` or `<reviewer_feedback>` is present, the previous attempt was rejected for exactly those reasons. Fix only the prescriptions or fields they name.
8. `<slots_to_fix>` names every slot an error was raised against: pass those slots to `load_exercise` and no others. When it names no slot, look up no exercises at all.
9. Use your tools when you need reference data. Do not invent a template or an exercise you could look up. Call `load_exercise` once per attempt, passing every slot you still have to fill in that one call.
10. Call `recall_memory` once before choosing the split. What it returns was stated or observed in earlier conversations: honour a preference it reports unless the profile or an injury rules it out, and let an adherence pattern it reports settle a choice the profile leaves open. It is not a substitute for the profile, and an empty result means plan from the profile alone.
11. Give every training day at least one exercise, and every exercise concrete sets and reps.

{security_block("<coaching_context>")}

## Output
Return the plan using the structured output schema.
Include training_days for every day `<current_plan>` shows you: the whole week normally, or only the narrowed days on a verification retry.
"""

COACH_CONTEXT_TEMPLATE = """
<coaching_context>
<user_profile>
{profile}
</user_profile>

<current_plan>
{plan}
</current_plan>

{slots_to_fix}
<feedback>
{feedback}
</feedback>
</coaching_context>
"""

VERIFICATION_ERRORS_TEMPLATE = """
<verification_errors>
{errors}
</verification_errors>
"""

REVIEWER_FEEDBACK_TEMPLATE = """
<reviewer_feedback>
{feedback}
</reviewer_feedback>
"""

SLOTS_TO_FIX_TEMPLATE = """
<slots_to_fix>
{slots}
</slots_to_fix>
"""

NO_SLOTS_TO_FIX = (
    "none - every prescription in the current plan passed; copy them all unchanged"
)

NUTRITION_TARGETS_TEMPLATE = """
<nutrition_targets>
{targets}
</nutrition_targets>
"""

NO_PLAN = "none - this is the user's first plan"


def build_coach_context(
    *,
    profile: str,
    plan: str | None,
    nutrition_targets: str | None = None,
    verification_errors: str | None = None,
    reviewer_feedback: str | None = None,
    slots_to_fix: str | None = None,
) -> str:
    """Build the XML-escaped context block the coach agent plans from."""

    feedback = ""
    if verification_errors:
        feedback += VERIFICATION_ERRORS_TEMPLATE.format(
            errors=escape(verification_errors)
        )
    if reviewer_feedback:
        feedback += REVIEWER_FEEDBACK_TEMPLATE.format(
            feedback=escape(reviewer_feedback)
        )

    context = COACH_CONTEXT_TEMPLATE.format(
        profile=escape(profile),
        plan=escape(plan) if plan else NO_PLAN,
        slots_to_fix=(
            SLOTS_TO_FIX_TEMPLATE.format(slots=escape(slots_to_fix))
            if slots_to_fix
            else ""
        ),
        feedback=feedback,
    )

    if not nutrition_targets:
        return context

    return context + NUTRITION_TARGETS_TEMPLATE.format(targets=nutrition_targets)
