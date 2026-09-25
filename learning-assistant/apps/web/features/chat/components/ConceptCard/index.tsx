import type { ConceptCardParams } from "@repo/shared/schemas";
import { Lightbulb } from "lucide-react";

import { ChatCard } from "@/features/chat/components/ChatCard";

/**
 * Every prop is optional: `useComponent` passes the tool arguments while they
 * are still streaming, so a field can be missing until the call is complete.
 */
export type ConceptCardProps = Partial<ConceptCardParams>;

/** Explains one term, drawn by `showConceptCard`. */
export const ConceptCard = ({
  term,
  definition,
  example,
}: ConceptCardProps) => (
  <ChatCard kind="concept" icon={Lightbulb} title={term}>
    {definition && (
      <p className="mt-2 leading-relaxed text-slate-700 dark:text-slate-200">
        {definition}
      </p>
    )}
    {example && (
      <p className="mt-2 rounded-lg bg-slate-50 px-2.5 py-2 whitespace-pre-wrap text-slate-700 dark:bg-slate-900/60 dark:text-slate-200">
        {example}
      </p>
    )}
  </ChatCard>
);
