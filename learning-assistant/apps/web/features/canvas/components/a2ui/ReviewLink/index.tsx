import { BookOpen } from "lucide-react";

import type { FeedbackComponentProps } from "@/features/canvas/types/feedback";
import { readText } from "@/features/canvas/utils/a2ui-props";
import { createReviewConceptAction } from "@/features/canvas/utils/feedback";

/** A link that opens the notes to review one concept. */
export const ReviewLink = ({
  props,
  dispatch,
}: FeedbackComponentProps<"ReviewLink">) => {
  const concept = readText(props.concept);

  const handleClick = () => {
    dispatch?.(createReviewConceptAction(concept));
  };

  return (
    <button
      type="button"
      onClick={handleClick}
      className="basis-full rounded-xl border border-indigo-200 bg-indigo-50 px-3 py-2 text-left text-xs font-medium text-indigo-700 transition-colors hover:bg-indigo-100 dark:border-indigo-800 dark:bg-indigo-950/50 dark:text-indigo-300 dark:hover:bg-indigo-900"
    >
      <span className="flex items-center gap-2">
        <BookOpen className="h-4 w-4 shrink-0" />
        {readText(props.label)}
      </span>
    </button>
  );
};
