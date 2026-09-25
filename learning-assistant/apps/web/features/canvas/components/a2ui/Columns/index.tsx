import { Fragment } from "react";

import type { BoardComponentProps } from "@/features/canvas/types/board";
import { readChildren } from "@/features/canvas/utils/a2ui-props";

/**
 * Children side by side once the Board is wide enough, stacked below that.
 * The Board is the container the width is measured against.
 */
export const Columns = ({
  props,
  children,
}: BoardComponentProps<"Columns">) => (
  <div className="grid grid-cols-1 items-start gap-4 @2xl:auto-cols-fr @2xl:grid-flow-col @2xl:grid-cols-none">
    {readChildren(props.children).map(({ id }) => (
      <Fragment key={id}>{children(id)}</Fragment>
    ))}
  </div>
);
