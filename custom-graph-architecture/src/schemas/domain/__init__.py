"""Domain models from the spec: the user, the catalogue, the templates and the plan."""

from src.schemas.domain.enums import (
    ActivityLevel,
    BodyRegion,
    DifficultyLevel,
    EquipmentType,
    FitnessGoal,
    InjuryStatus,
    MovementPattern,
    MuscleGroup,
    RestrictionAction,
    Sex,
)
from src.schemas.domain.exercise import (
    Exercise,
    ExerciseContraindication,
    ExerciseMuscleTarget,
    MusclePriority,
)
from src.schemas.domain.plan import (
    MacroTargets,
    NutritionTargets,
    PlanDay,
    PlannedExercise,
    TrainingPlan,
)
from src.schemas.domain.profile import (
    Injury,
    MovementRestriction,
    UserEquipment,
    UserProfile,
)
from src.schemas.domain.template import (
    ExerciseSlot,
    WorkoutDayTemplate,
    WorkoutTemplate,
)
from src.schemas.domain.verification import (
    CheckName,
    Severity,
    VerificationIssue,
    VerificationResult,
)

__all__ = [
    "ActivityLevel",
    "BodyRegion",
    "CheckName",
    "DifficultyLevel",
    "EquipmentType",
    "Exercise",
    "ExerciseContraindication",
    "ExerciseMuscleTarget",
    "ExerciseSlot",
    "FitnessGoal",
    "Injury",
    "InjuryStatus",
    "MacroTargets",
    "MovementPattern",
    "MovementRestriction",
    "MuscleGroup",
    "MusclePriority",
    "NutritionTargets",
    "PlanDay",
    "PlannedExercise",
    "RestrictionAction",
    "Severity",
    "Sex",
    "TrainingPlan",
    "UserEquipment",
    "UserProfile",
    "VerificationIssue",
    "VerificationResult",
    "WorkoutDayTemplate",
    "WorkoutTemplate",
]
