import {
  type CatalogDefinitions,
  createCatalog,
} from "@copilotkit/a2ui-renderer";
import { FEEDBACK_CATALOG_ID } from "@repo/shared/a2ui/feedback-catalog";
// zod 3 for the renderer's binder; see `a2ui-catalog.ts`.
import { z } from "zod3";

import { ConceptChip } from "@/features/canvas/components/a2ui/ConceptChip";
import { FeedbackCard } from "@/features/canvas/components/a2ui/FeedbackCard";
import { NextStepList } from "@/features/canvas/components/a2ui/NextStepList";
import { ReviewLink } from "@/features/canvas/components/a2ui/ReviewLink";

/**
 * The four components the Evaluator composes the Feedback surface from. The
 * server only accepts these (`@repo/shared/a2ui/feedback-catalog`); the props
 * here match that catalog.
 */
export const FEEDBACK_COMPONENT_DEFINITIONS = {
  FeedbackCard: {
    description: "Card with the overall feedback and its children.",
    props: z.object({
      title: z.string(),
      body: z.string(),
      children: z.array(z.string()).optional(),
    }),
  },
  ConceptChip: {
    description: "A concept with the student's mastery of it.",
    props: z.object({
      concept: z.string(),
      percent: z.number(),
      isWeakest: z.boolean().optional(),
    }),
  },
  ReviewLink: {
    description: "Opens the learning material to review one concept.",
    props: z.object({ label: z.string(), concept: z.string() }),
  },
  NextStepList: {
    description: "Ordered list of suggested next steps.",
    props: z.object({
      title: z.string().optional(),
      steps: z.array(z.string()),
    }),
  },
} satisfies CatalogDefinitions;

/** The catalog the dynamic Feedback surface renders with. */
export const FEEDBACK_UI_CATALOG = createCatalog(
  FEEDBACK_COMPONENT_DEFINITIONS,
  { FeedbackCard, ConceptChip, ReviewLink, NextStepList },
  { catalogId: FEEDBACK_CATALOG_ID, includeBasicCatalog: true },
);
