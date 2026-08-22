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
    """Specific muscle groups an exercise trains.

    The deltoid heads and the lats are listed separately from ``SHOULDERS`` and ``BACK``
    because the catalogue distinguishes them: a rear-delt slot filled by a lateral raise
    is a wrong prescription, and the coarse names cannot tell the two apart.
    """

    CHEST = "CHEST"
    BACK = "BACK"
    LATS = "LATS"
    SHOULDERS = "SHOULDERS"
    FRONT_DELTS = "FRONT_DELTS"
    SIDE_DELTS = "SIDE_DELTS"
    REAR_DELTS = "REAR_DELTS"
    BICEPS = "BICEPS"
    TRICEPS = "TRICEPS"
    FOREARMS = "FOREARMS"
    QUADS = "QUADS"
    HAMSTRINGS = "HAMSTRINGS"
    GLUTES = "GLUTES"
    CALVES = "CALVES"
    ABS = "ABS"
    OBLIQUES = "OBLIQUES"
    LOWER_BACK = "LOWER_BACK"
    HIP = "HIP"


class MovementPattern(StrEnum):
    """How an exercise loads the body.

    This is the filter a template slot is resolved with, so it has to be as fine-grained
    as the catalogue: one ``ISOLATION`` bucket would make a biceps slot and a calf slot
    the same query. The compound patterns are the spec's; the rest come from the
    catalogue's own taxonomy.
    """

    # Compound
    HORIZONTAL_PUSH = "HORIZONTAL_PUSH"
    HORIZONTAL_PULL = "HORIZONTAL_PULL"
    VERTICAL_PUSH = "VERTICAL_PUSH"
    VERTICAL_PULL = "VERTICAL_PULL"
    ANGLED_PUSH = "ANGLED_PUSH"
    DIP = "DIP"
    HIGH_PULL = "HIGH_PULL"
    SQUAT = "SQUAT"
    HINGE = "HINGE"
    LUNGE = "LUNGE"
    HIP_THRUST = "HIP_THRUST"
    CARRY = "CARRY"

    # Single joint
    ISOLATION = "ISOLATION"
    HORIZONTAL_ADDUCTION = "HORIZONTAL_ADDUCTION"
    ABDUCTION = "ABDUCTION"
    REAR_DELT_PULL = "REAR_DELT_PULL"
    SHOULDER_EXTENSION = "SHOULDER_EXTENSION"
    SCAPULAR = "SCAPULAR"
    ELBOW_FLEXION = "ELBOW_FLEXION"
    ELBOW_EXTENSION = "ELBOW_EXTENSION"
    KNEE_EXTENSION = "KNEE_EXTENSION"
    KNEE_FLEXION = "KNEE_FLEXION"
    HIP_FLEXION = "HIP_FLEXION"
    CALF_RAISE = "CALF_RAISE"

    # Trunk
    TRUNK_FLEXION = "TRUNK_FLEXION"
    ROTATION = "ROTATION"
    ANTI_ROTATION = "ANTI_ROTATION"
    ANTI_EXTENSION = "ANTI_EXTENSION"
    ANTI_LATERAL_FLEXION = "ANTI_LATERAL_FLEXION"
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
    PULL_UP_BAR = "PULL_UP_BAR"
    DIP_STATION = "DIP_STATION"
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
