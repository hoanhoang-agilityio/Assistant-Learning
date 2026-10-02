/** The chart's size and the room kept around the plot for labels. */
export interface ChartFrame {
  width: number;
  height: number;
  padding: { top: number; right: number; bottom: number; left: number };
}

/** One graded attempt placed on the chart. */
export interface TrendPoint {
  x: number;
  y: number;
  attemptNo: number;
  percent: number;
  submittedAt: string;
}

/** A horizontal grid line and its axis label. */
export interface GridLine {
  y: number;
  percent: number;
}

/** Everything the score chart draws, in its own coordinates. */
export interface ScoreTrend {
  points: TrendPoint[];
  /** The SVG path through the points; empty for a single attempt. */
  path: string;
  gridLines: GridLine[];
}

/** The headline numbers above a topic's chart. */
export interface TopicSummary {
  latestPercent: number;
  bestPercent: number;
  /** Latest minus first, in points; `null` with one attempt. */
  change: number | null;
}
