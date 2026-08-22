"""Enumerations from the spec's data-model section."""

from enum import StrEnum


class Sex(StrEnum):
    """User biological sex."""

    MALE = "MALE"
    FEMALE = "FEMALE"


class ActivityLevel(StrEnum):
    """Daily physical activity level, used to scale maintenance calories."""

    SEDENTARY = "SEDENTARY"
    LIGHT = "LIGHT"
    MODERATE = "MODERATE"
    VERY_ACTIVE = "VERY_ACTIVE"
    EXTRA_ACTIVE = "EXTRA_ACTIVE"


class FitnessGoal(StrEnum):
    """The user's primary training goal."""

    FAT_LOSS = "FAT_LOSS"
    MUSCLE_GAIN = "MUSCLE_GAIN"
    MAINTENANCE = "MAINTENANCE"
    STRENGTH = "STRENGTH"
    GENERAL_FITNESS = "GENERAL_FITNESS"


class BodyRegion(StrEnum):
    """Target body region of a training day or an exercise."""

    UPPER = "UPPER"
    LOWER = "LOWER"
    FULL_BODY = "FULL_BODY"
    CORE = "CORE"


class MuscleGroup(StrEnum):
    """Specific muscle groups an exercise trains."""

    CHEST = "CHEST"
    BACK = "BACK"
    SHOULDERS = "SHOULDERS"
    BICEPS = "BICEPS"
    TRICEPS = "TRICEPS"
    FOREARMS = "FOREARMS"
    QUADS = "QUADS"
    HAMSTRINGS = "HAMSTRINGS"
    GLUTES = "GLUTES"
    CALVES = "CALVES"
    ABS = "ABS"
    LOWER_BACK = "LOWER_BACK"
    HIP = "HIP"


class MovementPattern(StrEnum):
    """How an exercise loads the body, which is what injury restrictions act on."""

    HORIZONTAL_PUSH = "HORIZONTAL_PUSH"
    HORIZONTAL_PULL = "HORIZONTAL_PULL"
    VERTICAL_PUSH = "VERTICAL_PUSH"
    VERTICAL_PULL = "VERTICAL_PULL"
    SQUAT = "SQUAT"
    HINGE = "HINGE"
    LUNGE = "LUNGE"
    CARRY = "CARRY"
    ISOLATION = "ISOLATION"
    ROTATION = "ROTATION"
    ANTI_ROTATION = "ANTI_ROTATION"
    FLEXION = "FLEXION"
    EXTENSION = "EXTENSION"


class EquipmentType(StrEnum):
    """Standard equipment an exercise can require."""

    BODYWEIGHT = "BODYWEIGHT"
    BARBELL = "BARBELL"
    DUMBBELL = "DUMBBELL"
    CABLE = "CABLE"
    MACHINE = "MACHINE"
    KETTLEBELL = "KETTLEBELL"
    RESISTANCE_BAND = "RESISTANCE_BAND"
    SMITH_MACHINE = "SMITH_MACHINE"
    BENCH = "BENCH"
    OTHER = "OTHER"


class DifficultyLevel(StrEnum):
    """How much training experience an exercise assumes."""

    BEGINNER = "BEGINNER"
    INTERMEDIATE = "INTERMEDIATE"
    ADVANCED = "ADVANCED"


class InjuryStatus(StrEnum):
    """Whether an injury still constrains what the user may train."""

    ACTIVE = "ACTIVE"
    RECOVERING = "RECOVERING"
    RESOLVED = "RESOLVED"


class RestrictionAction(StrEnum):
    """How hard a restriction on a movement pattern is.

    The spec's value table for this enum repeats the ``InjuryStatus`` rows; the field
    description that names these three is the intended set.
    """

    PROHIBITED = "PROHIBITED"
    LIMITED = "LIMITED"
    ALLOWED = "ALLOWED"
