import { readList } from "@/features/canvas/utils/a2ui-props";
import type { ChatComponentProps } from "@/features/chat/types/chat-surface";

/** Ordered events on a vertical line. */
export const Timeline = ({ props }: ChatComponentProps<"Timeline">) => (
  <ol className="space-y-2 border-l-2 border-indigo-200 pl-3 dark:border-indigo-900/60">
    {readList<{ label: string; detail: string }>(props.items).map(
      ({ label, detail }, index) => (
        <li key={index} className="relative">
          <span className="absolute top-1 -left-[17px] h-2 w-2 rounded-full bg-indigo-500" />
          <span className="block font-semibold">{label}</span>
          <span className="block text-slate-600 dark:text-slate-300">
            {detail}
          </span>
        </li>
      ),
    )}
  </ol>
);
