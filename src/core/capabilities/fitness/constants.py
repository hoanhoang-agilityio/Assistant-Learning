"""Named domain constants for the fitness engine.

These are the safety-relevant numbers -- calorie floors, the protein ceiling,
training-day and weekly-set caps. They were previously buried at the top of a
file called utils.py. Names are preserved verbatim from that file; no value
was changed in the move.
"""

ACTIVITY_MULTIPLIERS = {
    "sedentary": 1.2,
    "gym_1x_week": 1.375,
    "gym_2x_week": 1.375,
    "gym_3x_week": 1.55,
    "gym_4x_week": 1.55,
    "gym_5x_week": 1.725,
    "gym_6x_week": 1.725,
}
DEFAULT_ACTIVITY_MULTIPLIER = 1.375
MIN_CALORIES_FEMALE = 1200
MIN_CALORIES_MALE = 1500
MAX_CALORIES = 4500
MAX_PROTEIN_G_PER_KG = 3.0
MAX_TRAINING_DAYS = 6
MAX_WEEKLY_SETS = 120
MIN_EXERCISE_SETS = 1
MAX_EXERCISE_SETS = 10

BODYWEIGHT_GYM_KEYWORDS = (
    "barbell",
    "smith machine",
    "cable",
    "leg press",
    "lat pulldown",
    "machine",
    "rack",
)

HOME_GYM_KEYWORDS = (
    "cable machine",
    "leg press",
    "smith machine",
    "lat pulldown",
    "hack squat",
)
