"""Calorie and macro arithmetic, shared by the coach agent and the QA agent."""

from src.schemas import (
    ActivityLevel,
    FitnessGoal,
    MacroTargets,
    NutritionTargets,
    Sex,
    UserProfile,
)

# Mifflin-St Jeor. The sex constant is the only term the two forms differ by.
SEX_CONSTANT: dict[Sex, int] = {Sex.MALE: 5, Sex.FEMALE: -161}

# The standard multipliers from basal rate to maintenance. The spec's activity levels
# already describe the user's exercise ("moderate exercise 3-5 days/week"), so training
# days are not counted a second time on top of them.
ACTIVITY_FACTORS: dict[ActivityLevel, float] = {
    ActivityLevel.SEDENTARY: 1.2,
    ActivityLevel.LIGHT: 1.375,
    ActivityLevel.MODERATE: 1.55,
    ActivityLevel.VERY_ACTIVE: 1.725,
    ActivityLevel.EXTRA_ACTIVE: 1.9,
}

# How far each goal moves the user off maintenance.
GOAL_ADJUSTMENTS: dict[FitnessGoal, float] = {
    FitnessGoal.FAT_LOSS: -0.20,
    FitnessGoal.MUSCLE_GAIN: 0.10,
    FitnessGoal.STRENGTH: 0.05,
    FitnessGoal.MAINTENANCE: 0.0,
    FitnessGoal.GENERAL_FITNESS: 0.0,
}

# Protein per kilogram of body weight. A deficit is the case where protein matters most,
# which is why the goal that subtracts calories asks for the most of it.
PROTEIN_G_PER_KG: dict[FitnessGoal, float] = {
    FitnessGoal.FAT_LOSS: 2.2,
    FitnessGoal.MUSCLE_GAIN: 2.0,
    FitnessGoal.STRENGTH: 2.0,
    FitnessGoal.MAINTENANCE: 1.8,
    FitnessGoal.GENERAL_FITNESS: 1.6,
}

FAT_G_PER_KG = 0.8

# The percentage adjustments are applied to a maintenance figure, so a small user's
# deficit lands lower than a large one's. These are the floors below which the number
# stops being a target and becomes a diet nobody should be handed.
CALORIE_FLOORS: dict[Sex, int] = {Sex.MALE: 1500, Sex.FEMALE: 1200}


def basal_metabolic_rate(profile: UserProfile) -> float:
    """Resting daily energy expenditure, by the Mifflin-St Jeor equation."""

    return (
        10 * profile.current_weight_kg
        + 6.25 * profile.height_cm
        - 5 * profile.age
        + SEX_CONSTANT[profile.sex]
    )


def maintenance_calories(bmr: float, activity_level: ActivityLevel) -> float:
    """What the user burns in a day at their activity level: the zero point of a goal."""

    return bmr * ACTIVITY_FACTORS[activity_level]


def goal_calories(tdee: float, goal: FitnessGoal, sex: Sex) -> float:
    """Maintenance moved by the goal's adjustment, held above the safety floor."""

    return max(tdee * (1 + GOAL_ADJUSTMENTS[goal]), CALORIE_FLOORS[sex])


def split_macros(kcal: float, weight_kg: float, goal: FitnessGoal) -> MacroTargets:
    """Split a calorie target three ways, protein and fat first."""

    protein_g = round(PROTEIN_G_PER_KG[goal] * weight_kg)
    fat_g = round(FAT_G_PER_KG * weight_kg)
    remaining = (
        kcal - MacroTargets(protein_g=protein_g, carbs_g=0, fat_g=fat_g).calories
    )

    return MacroTargets(
        protein_g=protein_g,
        carbs_g=max(0.0, round(remaining / 4)),
        fat_g=fat_g,
    )


def calc_macros(
    profile: UserProfile, goal: FitnessGoal | None = None
) -> NutritionTargets:
    """The user's daily calorie and macro targets, for their goal or a hypothetical one."""

    for_goal = goal or profile.goal
    bmr = basal_metabolic_rate(profile)
    tdee = maintenance_calories(bmr, profile.activity_level)
    macros = split_macros(
        goal_calories(tdee, for_goal, profile.sex), profile.current_weight_kg, for_goal
    )

    return NutritionTargets(
        goal=for_goal,
        bmr=round(bmr),
        tdee=round(tdee),
        daily_calories=round(macros.calories),
        macros=macros,
    )
