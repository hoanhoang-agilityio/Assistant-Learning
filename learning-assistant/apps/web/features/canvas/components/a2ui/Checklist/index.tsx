import { CheckCircle2, Circle } from "lucide-react";

import { CARD_CLASS } from "@/features/canvas/constants/canvas";
import type { BoardComponentProps } from "@/features/canvas/types/board";
import { readList, readText } from "@/features/canvas/utils/a2ui-props";

/**
 * Items with a tick for the done ones. Read-only: the ticks come from the
 * assistant, not from clicks.
 */
export const Checklist = ({ props }: BoardComponentProps<"Checklist">) => {
  const title = readText(props.title);

  return (
    <section className={CARD_CLASS}>
      {title && <h3 className="mb-3 text-base font-bold">{title}</h3>}
      <ul className="space-y-2 text-sm">
        {readList<{ text: string; done: boolean }>(props.items).map(
          ({ text, done }, index) => (
            <li key={index} className="flex items-start gap-2">
              {done ? (
                <CheckCircle2 className="mt-0.5 h-4 w-4 shrink-0 text-emerald-500" />
              ) : (
                <Circle className="mt-0.5 h-4 w-4 shrink-0 text-slate-400" />
              )}
              <span
                className={
                  done ? "text-slate-500 line-through dark:text-slate-400" : ""
                }
              >
                {text}
              </span>
            </li>
          ),
        )}
      </ul>
    </section>
  );
};
