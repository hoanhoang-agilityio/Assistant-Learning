import type { GradedAttempt, TopicHistory } from "@repo/shared/schemas";

import {
  HISTORY_DATE_FORMAT,
  HISTORY_LOCALE,
  SCORE_GRID_PERCENTS,
} from "@/features/history/constants/history";
import type {
  ChartFrame,
  ScoreTrend,
  TopicSummary,
} from "@/features/history/types/history";

/**
 * Places each attempt on the chart: evenly spaced in attempt order (they
 * can be minutes or weeks apart, so time would bunch them), 0–100% from the
 * bottom of the plot to its top. A single attempt sits in the middle.
 */
export const calculateScoreTrend = (
  attempts: readonly GradedAttempt[],
  { width, height, padding }: ChartFrame,
): ScoreTrend => {
  const plotWidth = width - padding.left - padding.right;
  const plotHeight = height - padding.top - padding.bottom;
  const toY = (percent: number) =>
    padding.top + plotHeight * (1 - Math.min(Math.max(percent, 0), 100) / 100);
  const step = attempts.length > 1 ? plotWidth / (attempts.length - 1) : 0;

  const points = attempts.map(({ attemptNo, score, submittedAt }, index) => ({
    x:
      attempts.length > 1
        ? padding.left + step * index
        : padding.left + plotWidth / 2,
    y: toY(score.percent),
    attemptNo,
    percent: score.percent,
    submittedAt,
  }));
  const path =
    points.length > 1
      ? points
          .map(({ x, y }, index) => `${index === 0 ? "M" : "L"}${x} ${y}`)
          .join(" ")
      : "";

  return {
    points,
    path,
    gridLines: SCORE_GRID_PERCENTS.map((percent) => ({
      percent,
      y: toY(percent),
    })),
  };
};

/** Latest and best score, and how far the latest moved from the first. */
export const summarizeTopic = ({ attempts }: TopicHistory): TopicSummary => {
  const percents = attempts.map(({ score }) => score.percent);
  const first = percents[0] ?? 0;
  const latest = percents.at(-1) ?? 0;

  return {
    latestPercent: latest,
    bestPercent: Math.max(...percents, 0),
    change: percents.length > 1 ? latest - first : null,
  };
};

/** "+35", "−10" or "±0": a change in points, with its sign. */
export const formatScoreChange = (change: number): string => {
  if (change > 0) {
    return `+${change}`;
  }
  return change < 0 ? `−${Math.abs(change)}` : "±0";
};

/** "Oct 2": when an attempt was graded, in UTC so server and tests agree. */
export const formatAttemptDate = (submittedAt: string): string =>
  new Intl.DateTimeFormat(HISTORY_LOCALE, {
    ...HISTORY_DATE_FORMAT,
    timeZone: "UTC",
  }).format(new Date(submittedAt));
