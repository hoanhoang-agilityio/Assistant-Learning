import { Sparkles } from "lucide-react";
import { Fragment } from "react";

import { CARD_CLASS } from "@/features/canvas/constants/canvas";
import type { FeedbackComponentProps } from "@/features/canvas/types/feedback";
import { readChildren, readText } from "@/features/canvas/utils/a2ui-props";

/** The Evaluator's feedback: headline, body, then its chips, links and steps. */
export const FeedbackCard = ({
  props,
  children,
}: FeedbackComponentProps<"FeedbackCard">) => (
  <section className={CARD_CLASS}>
    <h3 className="mb-2 flex items-center gap-2 text-base font-bold">
      <Sparkles className="h-5 w-5 text-indigo-500" />
      {readText(props.title)}
    </h3>
    <p className="mb-4 text-sm leading-relaxed whitespace-pre-wrap text-slate-600 dark:text-slate-300">
      {readText(props.body)}
    </p>
    <div className="flex flex-wrap items-start gap-2">
      {readChildren(props.children).map(({ id }) => (
        <Fragment key={id}>{children(id)}</Fragment>
      ))}
    </div>
  </section>
);
