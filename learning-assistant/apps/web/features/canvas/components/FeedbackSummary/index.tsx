import { MessageCircle } from "lucide-react";

import { CARD_CLASS } from "@/features/canvas/constants/canvas";

export interface FeedbackSummaryProps {
  summary: string;
}

/** The plain feedback text, shown when there is no surface to draw. */
export const FeedbackSummary = ({ summary }: FeedbackSummaryProps) => (
  <section className={CARD_CLASS}>
    <h3 className="mb-2 flex items-center gap-2 text-base font-bold">
      <MessageCircle className="h-5 w-5 text-indigo-500" /> Your Feedback
    </h3>
    <p className="text-sm leading-relaxed whitespace-pre-wrap text-slate-600 dark:text-slate-300">
      {summary}
    </p>
  </section>
);
