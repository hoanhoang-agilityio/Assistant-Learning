import type { Tier } from "@repo/shared/schemas";

import type { Tone } from "@/features/canvas/types/a2ui";

/** Tiles and bars take the colour of the tier their percent falls in. */
export const TIER_TONE: Record<Tier, Tone> = {
  Novice: "rose",
  Practitioner: "amber",
  Master: "emerald",
};

/** What each tier means, under the badge on the Score stage. */
export const TIER_DESCRIPTIONS: Record<Tier, string> = {
  Novice:
    "You're building the foundations. Review your notes, then retake the quiz.",
  Practitioner:
    "You understand the core ideas. A little more practice gets you to Master.",
  Master:
    "You've mastered this topic. Try new questions or move on to a new topic.",
};

/** Labels of the stat tiles (Evaluation) and stat chips (Score). */
export const RESULT_LABELS = {
  accuracy: "Accuracy",
  correctAnswers: "Correct Answers",
  weakestConcept: "Weakest Concept",
  correct: "Correct",
  conceptsMastered: "Concepts Mastered",
  nextTier: "Next Tier",
} as const;

/** Shown as the weakest concept when every concept was answered perfectly. */
export const NO_WEAKEST_CONCEPT = "None";

export const TOP_TIER_REACHED = "Top tier";

/** Tag on the weakest concept's mastery bar. */
export const WEAKEST_LABEL = "Weakest";

/** Text colour of a stat value in each tone. */
export const TONE_TEXT_CLASS: Record<Tone, string> = {
  indigo: "text-indigo-600 dark:text-indigo-400",
  emerald: "text-emerald-600 dark:text-emerald-400",
  amber: "text-amber-600 dark:text-amber-400",
  rose: "text-rose-600 dark:text-rose-400",
};

/** Fill colour of a bar in each tone. */
export const TONE_FILL_CLASS: Record<Tone, string> = {
  indigo: "bg-indigo-500",
  emerald: "bg-emerald-500",
  amber: "bg-amber-500",
  rose: "bg-rose-500",
};
