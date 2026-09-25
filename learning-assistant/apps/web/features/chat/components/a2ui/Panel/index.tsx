import { LayoutPanelTop } from "lucide-react";
import { Fragment } from "react";

import { readChildren, readText } from "@/features/canvas/utils/a2ui-props";
import type { ChatComponentProps } from "@/features/chat/types/chat-surface";

/** Root of a chat surface: a titled card with its children stacked. */
export const Panel = ({ props, children }: ChatComponentProps<"Panel">) => (
  <section className="rounded-xl border border-indigo-200 bg-white p-3 text-xs shadow-sm dark:border-indigo-900/60 dark:bg-slate-800">
    <h3 className="mb-2 flex items-center gap-2 text-sm font-semibold">
      <LayoutPanelTop className="h-4 w-4 shrink-0 text-indigo-500" />
      {readText(props.title)}
    </h3>
    <div className="space-y-2.5">
      {readChildren(props.children).map(({ id }) => (
        <Fragment key={id}>{children(id)}</Fragment>
      ))}
    </div>
  </section>
);
