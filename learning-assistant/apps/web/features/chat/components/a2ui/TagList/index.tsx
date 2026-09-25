import { readList } from "@/features/canvas/utils/a2ui-props";
import type { ChatComponentProps } from "@/features/chat/types/chat-surface";

/** Keywords as small tags. */
export const TagList = ({ props }: ChatComponentProps<"TagList">) => (
  <div className="flex flex-wrap gap-1.5">
    {readList<string>(props.tags).map((tag, index) => (
      <span
        key={index}
        className="rounded-full bg-indigo-50 px-2 py-0.5 font-medium text-indigo-700 dark:bg-indigo-950/50 dark:text-indigo-300"
      >
        {tag}
      </span>
    ))}
  </div>
);
