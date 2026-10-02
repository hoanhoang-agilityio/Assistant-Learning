import type { ChartFrame } from "@/features/history/types/history";

/**
 * The score chart's size and label room. Its width is replaced by the
 * card's once measured; this one is drawn until then.
 */
export const SCORE_TREND_FRAME: ChartFrame = {
  width: 480,
  height: 132,
  padding: { top: 12, right: 40, bottom: 24, left: 34 },
};

/** Where the chart draws grid lines, in percent. */
export const SCORE_GRID_PERCENTS = [0, 50, 100] as const;

/** How an attempt's date is written, e.g. "Oct 2". */
export const HISTORY_DATE_FORMAT: Intl.DateTimeFormatOptions = {
  month: "short",
  day: "numeric",
};

export const HISTORY_LOCALE = "en";

export const HISTORY_COPY = {
  title: "Progress",
  intro:
    "Every topic you were quizzed on: your scores over time and how well you know each concept.",
  back: "Back to the assistant",
  empty: "No graded quizzes yet. Take a quiz and your scores show here.",
  untitled: "Untitled topic",
  latest: "Latest",
  best: "Best",
  sinceFirst: "since the first try",
  scores: "Scores by attempt",
  attempt: "Attempt",
  date: "Graded",
  score: "Score",
  mastery: "Concept mastery, latest attempt",
  noMastery: "No concepts were tagged in this quiz.",
  weak: "Weak",
  retake: "Retake",
} as const;
