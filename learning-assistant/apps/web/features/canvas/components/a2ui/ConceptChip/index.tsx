import { getTier } from "@repo/shared/utils/tier";

import {
  TIER_TONE,
  TONE_TEXT_CLASS,
} from "@/features/canvas/constants/results";
import type { FeedbackComponentProps } from "@/features/canvas/types/feedback";
import {
  readBoolean,
  readNumber,
  readText,
} from "@/features/canvas/utils/a2ui-props";

/** A concept and its mastery, outlined in amber when it is the weakest. */
export const ConceptChip = ({
  props,
}: FeedbackComponentProps<"ConceptChip">) => {
  const percent = readNumber(props.percent) ?? 0;
  const isWeakest = readBoolean(props.isWeakest);

  return (
    <span
      className={`inline-flex items-center gap-2 rounded-full border px-3 py-1 text-xs ${
        isWeakest
          ? "border-amber-400 bg-amber-50 dark:border-amber-600 dark:bg-amber-950/40"
          : "border-slate-200 bg-slate-50 dark:border-slate-700 dark:bg-slate-900"
      }`}
    >
      <span className="font-medium">{readText(props.concept)}</span>
      <span
        className={`font-semibold ${TONE_TEXT_CLASS[TIER_TONE[getTier(percent)]]}`}
      >
        {percent}%
      </span>
    </span>
  );
};
