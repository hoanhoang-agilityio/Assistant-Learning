import { type LucideIcon, ThumbsDown, ThumbsUp } from "lucide-react";

import type { BoardComponentProps } from "@/features/canvas/types/board";
import { readList, readText } from "@/features/canvas/utils/a2ui-props";

interface SideProps {
  title: string;
  items: string[];
  icon: LucideIcon;
  className: string;
}

const Side = ({ title, items, icon: Icon, className }: SideProps) => (
  <div className={`rounded-xl border p-4 ${className}`}>
    <h4 className="mb-2 flex items-center gap-1.5 text-sm font-semibold">
      <Icon className="h-4 w-4" />
      {title}
    </h4>
    <ul className="list-inside list-disc space-y-1 text-sm leading-relaxed">
      {items.map((item, index) => (
        <li key={index}>{item}</li>
      ))}
    </ul>
  </div>
);

/** Advantages and drawbacks side by side, stacked on a narrow Board. */
export const ProsCons = ({ props }: BoardComponentProps<"ProsCons">) => (
  <div className="grid gap-4 @xl:grid-cols-2">
    <Side
      title={readText(props.prosTitle)}
      items={readList<string>(props.pros)}
      icon={ThumbsUp}
      className="border-emerald-200 bg-emerald-50 text-emerald-900 dark:border-emerald-900/60 dark:bg-emerald-950/40 dark:text-emerald-100"
    />
    <Side
      title={readText(props.consTitle)}
      items={readList<string>(props.cons)}
      icon={ThumbsDown}
      className="border-rose-200 bg-rose-50 text-rose-900 dark:border-rose-900/60 dark:bg-rose-950/40 dark:text-rose-100"
    />
  </div>
);
