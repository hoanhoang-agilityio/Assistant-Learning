import { Fragment } from "react";

import { readChildren, readText } from "@/features/canvas/utils/a2ui-props";
import type { ChatComponentProps } from "@/features/chat/types/chat-surface";

/** A headed group inside the Panel. */
export const Section = ({ props, children }: ChatComponentProps<"Section">) => (
  <div>
    <h4 className="mb-1.5 text-[11px] font-semibold tracking-wide text-slate-500 uppercase dark:text-slate-400">
      {readText(props.heading)}
    </h4>
    <div className="space-y-2">
      {readChildren(props.children).map(({ id }) => (
        <Fragment key={id}>{children(id)}</Fragment>
      ))}
    </div>
  </div>
);
