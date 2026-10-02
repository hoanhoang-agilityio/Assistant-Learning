import type { GradedAttempt } from "@repo/shared/schemas";
import type { RefObject } from "react";

import { HISTORY_COPY } from "@/features/history/constants/history";
import type { ChartFrame, ScoreTrend } from "@/features/history/types/history";
import { formatAttemptDate } from "@/features/history/utils/score-trend";

export interface ScoreTrendChartViewProps {
  /** Oldest first, for the table. */
  attempts: readonly GradedAttempt[];
  /** Names the chart for screen readers, e.g. the topic. */
  label: string;
  /** The chart drawn at `frame.width`, the figure's measured width. */
  frame: ChartFrame;
  trend: ScoreTrend;
  figureRef: RefObject<HTMLElement | null>;
}

/** Up to this many attempts each get their number under the axis. */
const MAX_LABELLED_ATTEMPTS = 8;
const TOOLTIP_WIDTH = 116;
const TOOLTIP_HEIGHT = 20;
const TOOLTIP_GAP = 10;
const POINT_RADIUS = 4;
const HIT_RADIUS = 12;

/**
 * One topic's scores by attempt: a 2px line with ringed points, 0/50/100%
 * grid lines, the latest score labelled at the end, and each point's
 * attempt, score and date on hover or focus (CSS only). Drawn at the
 * figure's own width, so text keeps its size. A visually hidden table
 * carries the same numbers.
 */
export const ScoreTrendChartView = ({
  attempts,
  label,
  frame: { width, height, padding },
  trend: { points, path, gridLines },
  figureRef,
}: ScoreTrendChartViewProps) => {
  const last = points.at(-1);
  const isLabellingEvery = points.length <= MAX_LABELLED_ATTEMPTS;

  return (
    <figure ref={figureRef}>
      <svg
        viewBox={`0 0 ${width} ${height}`}
        width={width}
        height={height}
        role="img"
        aria-label={`${HISTORY_COPY.scores}: ${label}`}
        className="block max-w-full overflow-visible"
      >
        {gridLines.map(({ y, percent }) => (
          <g key={percent}>
            <line
              x1={padding.left}
              x2={width - padding.right}
              y1={y}
              y2={y}
              className="stroke-slate-200 dark:stroke-slate-700"
              strokeWidth={1}
            />
            <text
              x={padding.left - 8}
              y={y}
              textAnchor="end"
              dominantBaseline="middle"
              className="fill-slate-400 text-[10px] tabular-nums"
            >
              {percent}%
            </text>
          </g>
        ))}

        {points.map(({ x, attemptNo }, index) =>
          isLabellingEvery || index === 0 || index === points.length - 1 ? (
            <text
              key={attemptNo}
              x={x}
              y={height - 6}
              textAnchor="middle"
              className="fill-slate-400 text-[10px] tabular-nums"
            >
              #{attemptNo}
            </text>
          ) : null,
        )}

        {path && (
          <path
            d={path}
            fill="none"
            strokeWidth={2}
            strokeLinecap="round"
            strokeLinejoin="round"
            className="stroke-indigo-600 dark:stroke-indigo-500"
          />
        )}

        {last && (
          <text
            x={last.x + 10}
            y={last.y}
            dominantBaseline="middle"
            className="fill-slate-700 text-[11px] font-semibold tabular-nums dark:fill-slate-200"
          >
            {last.percent}%
          </text>
        )}

        {points.map(({ x, y, attemptNo, percent, submittedAt }) => {
          const tooltipX = Math.min(
            Math.max(x - TOOLTIP_WIDTH / 2, 0),
            width - TOOLTIP_WIDTH,
          );
          // Above the point, or below it when there is no room above.
          const above = y - TOOLTIP_HEIGHT - TOOLTIP_GAP;
          const tooltipY = above >= 0 ? above : y + TOOLTIP_GAP;
          const text = `${HISTORY_COPY.attempt} ${attemptNo} · ${percent}% · ${formatAttemptDate(submittedAt)}`;

          return (
            <g
              key={attemptNo}
              tabIndex={0}
              aria-label={text}
              className="group outline-none"
            >
              <circle cx={x} cy={y} r={HIT_RADIUS} fill="transparent" />
              <circle
                cx={x}
                cy={y}
                r={POINT_RADIUS}
                strokeWidth={2}
                className="fill-indigo-600 stroke-white group-hover:fill-indigo-700 group-focus:fill-indigo-700 dark:fill-indigo-500 dark:stroke-slate-800"
              />
              <g className="pointer-events-none opacity-0 transition-opacity group-hover:opacity-100 group-focus:opacity-100">
                <rect
                  x={tooltipX}
                  y={tooltipY}
                  width={TOOLTIP_WIDTH}
                  height={TOOLTIP_HEIGHT}
                  rx={4}
                  className="fill-slate-900 dark:fill-slate-100"
                />
                <text
                  x={tooltipX + TOOLTIP_WIDTH / 2}
                  y={tooltipY + TOOLTIP_HEIGHT / 2}
                  textAnchor="middle"
                  dominantBaseline="middle"
                  className="fill-white text-[10px] tabular-nums dark:fill-slate-900"
                >
                  {text}
                </text>
              </g>
            </g>
          );
        })}
      </svg>

      <table className="sr-only">
        <caption>
          {HISTORY_COPY.scores}: {label}
        </caption>
        <thead>
          <tr>
            <th scope="col">{HISTORY_COPY.attempt}</th>
            <th scope="col">{HISTORY_COPY.date}</th>
            <th scope="col">{HISTORY_COPY.score}</th>
          </tr>
        </thead>
        <tbody>
          {attempts.map(({ attemptNo, score, submittedAt }) => (
            <tr key={attemptNo}>
              <td>{attemptNo}</td>
              <td>{formatAttemptDate(submittedAt)}</td>
              <td>
                {score.percent}% ({score.tier})
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </figure>
  );
};
