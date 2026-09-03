"""Domain models from the spec: the user, the catalogue, the templates and the plan."""

from src.schemas.domain.exercise import (
    Exercise,
    ExerciseContraindication,
)
from src.schemas.domain.plan import (
    MacroTargets,
    NeedsProfile,
    NutritionTargets,
    PlanAnswer,
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
    "CheckName",
    "Exercise",
    "ExerciseContraindication",
    "ExerciseSlot",
    "Injury",
    "MacroTargets",
    "MovementRestriction",
    "NeedsProfile",
    "NutritionTargets",
    "PlanAnswer",
    "PlanDay",
    "PlannedExercise",
    "Severity",
    "TrainingPlan",
    "UserEquipment",
    "UserProfile",
    "VerificationIssue",
    "VerificationResult",
    "WorkoutDayTemplate",
    "WorkoutTemplate",
]
