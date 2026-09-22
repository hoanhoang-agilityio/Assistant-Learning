import { CARD_CLASS } from "@/features/canvas/constants/canvas";
import type { CanvasComponentProps } from "@/features/canvas/types/a2ui";
import { readNumber, readText } from "@/features/canvas/utils/a2ui-props";

/** The score card: the tier badge, the final score, then the stat chips. */
export const ScoreCard = ({
  props,
  children,
}: CanvasComponentProps<"ScoreCard">) => (
  <section className={`${CARD_CLASS} p-8 text-center`}>
    {props.badge && children(props.badge)}

    <div className="mt-6 inline-flex items-center gap-2 rounded-xl border border-slate-200 bg-slate-100 px-4 py-2 dark:border-slate-800 dark:bg-slate-900">
      <span className="text-xs text-slate-400">{readText(props.label)}:</span>
      <span className="text-lg font-black text-indigo-600 dark:text-indigo-400">
        {readNumber(props.percent) ?? 0} / 100
      </span>
    </div>

    {props.chips && (
      <div className="mt-8 border-t border-slate-100 pt-6 dark:border-slate-700/60">
        {children(props.chips)}
      </div>
    )}
  </section>
);
