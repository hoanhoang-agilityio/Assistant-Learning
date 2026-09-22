import { BarChart2 } from "lucide-react";

import { CARD_CLASS } from "@/features/canvas/constants/canvas";
import { TONE_TEXT_CLASS } from "@/features/canvas/constants/results";
import type { CanvasComponentProps } from "@/features/canvas/types/a2ui";
import { readStatTiles, readText } from "@/features/canvas/utils/a2ui-props";

/** A card of headline numbers, then one child (the mastery bars). */
export const StatTiles = ({
  props,
  children,
}: CanvasComponentProps<"StatTiles">) => (
  <section className={CARD_CLASS}>
    <h3 className="mb-4 flex items-center gap-2 text-base font-bold">
      <BarChart2 className="h-5 w-5 text-indigo-500" />
      {readText(props.title)}
    </h3>

    <dl className="mb-6 grid grid-cols-1 gap-4 md:grid-cols-3">
      {readStatTiles(props.tiles).map(({ label, value, tone }) => (
        <div
          key={label}
          className="rounded-xl border border-slate-200 bg-slate-50 p-4 text-center dark:border-slate-700 dark:bg-slate-900"
        >
          <dt className="text-xs text-slate-400">{label}</dt>
          <dd
            className={`mt-1 truncate text-2xl font-extrabold ${TONE_TEXT_CLASS[tone]}`}
            title={value}
          >
            {value}
          </dd>
        </div>
      ))}
    </dl>

    {props.child && children(props.child)}
  </section>
);
