"use client";

import type { GradedAttempt } from "@repo/shared/schemas";

import { ScoreTrendChartView } from "@/features/history/components/ScoreTrendChartView";
import { SCORE_TREND_FRAME } from "@/features/history/constants/history";
import { useElementWidth } from "@/features/history/hooks/use-element-width";
import { calculateScoreTrend } from "@/features/history/utils/score-trend";

export interface ScoreTrendChartProps {
  /** Oldest first. */
  attempts: readonly GradedAttempt[];
  /** Names the chart for screen readers, e.g. the topic. */
  label: string;
}

/** A topic's scores by attempt, laid out for the width the card gives it. */
export const ScoreTrendChart = ({ attempts, label }: ScoreTrendChartProps) => {
  const { ref, width } = useElementWidth<HTMLElement>(SCORE_TREND_FRAME.width);
  const frame = { ...SCORE_TREND_FRAME, width };

  return (
    <ScoreTrendChartView
      attempts={attempts}
      label={label}
      frame={frame}
      trend={calculateScoreTrend(attempts, frame)}
      figureRef={ref}
    />
  );
};
