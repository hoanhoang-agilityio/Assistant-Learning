import { Fragment } from "react";

import type {
  BuildChild,
  CanvasComponentProps,
} from "@/features/canvas/types/a2ui";
import { readChildren } from "@/features/canvas/utils/a2ui-props";

/**
 * Root layout of a canvas surface: its children, evenly spaced. A template
 * child list renders the same component once per item, at that item's path.
 */
export const Stack = ({ props, children }: CanvasComponentProps<"Stack">) => {
  const buildChild: BuildChild = children;

  return (
    <div className="space-y-6">
      {readChildren(props.children).map(({ id, basePath }) => (
        <Fragment key={basePath ?? id}>{buildChild(id, basePath)}</Fragment>
      ))}
    </div>
  );
};
