import { Fragment } from "react";

import type { CanvasComponentProps } from "@/features/canvas/types/a2ui";

/** Root layout of a canvas surface: its children, evenly spaced. */
export const Stack = ({ props, children }: CanvasComponentProps<"Stack">) => (
  <div className="space-y-6">
    {props.children.map((id) => (
      <Fragment key={id}>{children(id)}</Fragment>
    ))}
  </div>
);
