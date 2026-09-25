import { readNumber, readText } from "@/features/canvas/utils/a2ui-props";
import type { ChatComponentProps } from "@/features/chat/types/chat-surface";

/** A labelled bar, clamped to 0–100. */
export const Meter = ({ props }: ChatComponentProps<"Meter">) => {
  const percent = Math.min(100, Math.max(0, readNumber(props.percent) ?? 0));

  return (
    <div>
      <div className="mb-1 flex justify-between">
        <span className="font-medium">{readText(props.label)}</span>
        <span className="text-slate-500 dark:text-slate-400">
          {Math.round(percent)}%
        </span>
      </div>
      <div className="h-1.5 overflow-hidden rounded-full bg-slate-200 dark:bg-slate-700">
        <div
          className="h-full rounded-full bg-indigo-500"
          style={{ width: `${percent}%` }}
        />
      </div>
    </div>
  );
};
