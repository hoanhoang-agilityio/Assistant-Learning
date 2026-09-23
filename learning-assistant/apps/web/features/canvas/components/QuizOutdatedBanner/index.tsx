import { RefreshCw } from "lucide-react";

import { QUIZ_OUTDATED_TEXT } from "@/features/canvas/constants/material";

/** Shown after a learning material change cleared the quiz and its results. */
export const QuizOutdatedBanner = () => (
  <div
    role="status"
    className="flex items-start gap-2 rounded-xl border border-amber-500/30 bg-amber-500/10 px-4 py-3 text-xs text-amber-800 dark:text-amber-200"
  >
    <RefreshCw className="mt-0.5 h-4 w-4 shrink-0" />
    <p>
      <strong className="font-semibold">Quiz out of date.</strong>{" "}
      {QUIZ_OUTDATED_TEXT}
    </p>
  </div>
);
