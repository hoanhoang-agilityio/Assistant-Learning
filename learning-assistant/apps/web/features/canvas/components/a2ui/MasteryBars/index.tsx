import {
  TONE_FILL_CLASS,
  TONE_TEXT_CLASS,
  WEAKEST_LABEL,
} from "@/features/canvas/constants/results";
import type { CanvasComponentProps } from "@/features/canvas/types/a2ui";
import { readMasteryItems, readText } from "@/features/canvas/utils/a2ui-props";

/** One labelled progress bar per concept, the weakest one marked. */
export const MasteryBars = ({ props }: CanvasComponentProps<"MasteryBars">) => {
  const items = readMasteryItems(props.items);

  return (
    <div className="space-y-3">
      <h4 className="text-xs font-semibold tracking-wider text-slate-500 uppercase">
        {readText(props.title)}
      </h4>
      {items.length === 0 && (
        <p className="text-xs text-slate-400">{readText(props.emptyText)}</p>
      )}
      {items.map(({ concept, percent, tone, isWeakest }) => (
        <div key={concept}>
          <div className="mb-1 flex items-center justify-between gap-2 text-xs">
            <span className="flex min-w-0 items-center gap-2">
              <span className="truncate">{concept}</span>
              {isWeakest && (
                <span className="shrink-0 rounded-full bg-amber-100 px-2 py-0.5 text-[10px] font-semibold text-amber-700 dark:bg-amber-950/60 dark:text-amber-300">
                  {WEAKEST_LABEL}
                </span>
              )}
            </span>
            <span className={`font-semibold ${TONE_TEXT_CLASS[tone]}`}>
              {percent}%
            </span>
          </div>
          <div
            role="progressbar"
            aria-label={concept}
            aria-valuenow={percent}
            aria-valuemin={0}
            aria-valuemax={100}
            className="h-2 w-full overflow-hidden rounded-full bg-slate-200 dark:bg-slate-700"
          >
            <div
              className={`h-full rounded-full ${TONE_FILL_CLASS[tone]}`}
              style={{ width: `${percent}%` }}
            />
          </div>
        </div>
      ))}
    </div>
  );
};
