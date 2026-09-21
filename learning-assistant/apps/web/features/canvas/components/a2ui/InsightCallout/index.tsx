import { Lightbulb } from "lucide-react";

import type { CanvasComponentProps } from "@/features/canvas/types/a2ui";
import { readText } from "@/features/canvas/utils/a2ui-props";

/** A highlighted key idea with a lightbulb. */
export const InsightCallout = ({
  props,
}: CanvasComponentProps<"InsightCallout">) => {
  const label = readText(props.label);
  return (
    <div className="flex items-start gap-3 rounded-xl border border-indigo-100 bg-indigo-50/50 p-4 text-xs text-indigo-900 dark:border-indigo-900/50 dark:bg-indigo-950/30 dark:text-indigo-200">
      <Lightbulb className="mt-0.5 h-5 w-5 shrink-0 text-indigo-500" />
      <p>
        {label && <strong>{label}: </strong>}
        {readText(props.text)}
      </p>
    </div>
  );
};
