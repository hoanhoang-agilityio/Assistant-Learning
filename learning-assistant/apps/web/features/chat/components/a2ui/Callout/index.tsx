import { Info, Lightbulb, TriangleAlert } from "lucide-react";

import { readText } from "@/features/canvas/utils/a2ui-props";
import type { ChatComponentProps } from "@/features/chat/types/chat-surface";

const TONES = {
  info: {
    Icon: Info,
    className:
      "border-sky-200 bg-sky-50 text-sky-800 dark:border-sky-900/60 dark:bg-sky-950/40 dark:text-sky-200",
  },
  tip: {
    Icon: Lightbulb,
    className:
      "border-emerald-200 bg-emerald-50 text-emerald-800 dark:border-emerald-900/60 dark:bg-emerald-950/40 dark:text-emerald-200",
  },
  warning: {
    Icon: TriangleAlert,
    className:
      "border-amber-200 bg-amber-50 text-amber-800 dark:border-amber-900/60 dark:bg-amber-950/40 dark:text-amber-200",
  },
} as const;

/** One highlighted sentence; an unknown tone falls back to info. */
export const Callout = ({ props }: ChatComponentProps<"Callout">) => {
  const tone =
    props.tone === "tip" || props.tone === "warning" ? props.tone : "info";
  const { Icon, className } = TONES[tone];

  return (
    <div
      className={`flex gap-2 rounded-lg border px-2.5 py-2 leading-relaxed ${className}`}
    >
      <Icon className="mt-0.5 h-3.5 w-3.5 shrink-0" />
      <span>{readText(props.text)}</span>
    </div>
  );
};
