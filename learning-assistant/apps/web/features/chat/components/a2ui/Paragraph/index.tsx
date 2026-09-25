import { readText } from "@/features/canvas/utils/a2ui-props";
import type { ChatComponentProps } from "@/features/chat/types/chat-surface";

/** Plain text. */
export const Paragraph = ({ props }: ChatComponentProps<"Paragraph">) => (
  <p className="leading-relaxed whitespace-pre-wrap text-slate-700 dark:text-slate-200">
    {readText(props.text)}
  </p>
);
