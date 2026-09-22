import type { CanvasComponentProps } from "@/features/canvas/types/a2ui";
import { readStatChips } from "@/features/canvas/utils/a2ui-props";

/** A row of small value-over-label stats. */
export const StatChips = ({ props }: CanvasComponentProps<"StatChips">) => (
  <dl className="flex flex-wrap justify-center gap-6">
    {readStatChips(props.chips).map(({ label, value }) => (
      <div key={label} className="flex flex-col-reverse text-center">
        <dt className="text-[11px] text-slate-400">{label}</dt>
        <dd className="text-xl font-bold">{value}</dd>
      </div>
    ))}
  </dl>
);
