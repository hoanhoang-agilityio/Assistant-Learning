import { z } from "zod";

import { ROOT_COMPONENT_ID } from "../a2ui/canvas-catalog";

/**
 * The `render_a2ui` arguments the Evaluator may send: a flat A2UI v0.9
 * component list built only from the Feedback catalog, with literal values
 * (no data bindings). Each component's props are declared here so the model's
 * output is constrained by type, not only checked afterwards. It mirrors
 * `FEEDBACK_CATALOG`; every prop is required so strict tool schemas accept it.
 */
const ComponentIdSchema = z
  .string()
  .min(1)
  .describe("Unique id; the FeedbackCard's id is root");

const FeedbackCardSchema = z.object({
  id: ComponentIdSchema,
  component: z.literal("FeedbackCard"),
  title: z.string().min(1),
  body: z.string().min(1),
  children: z.array(z.string().min(1)),
});

const ConceptChipSchema = z.object({
  id: ComponentIdSchema,
  component: z.literal("ConceptChip"),
  concept: z.string().min(1),
  percent: z.number().min(0).max(100),
  isWeakest: z.boolean(),
});

const ReviewLinkSchema = z.object({
  id: ComponentIdSchema,
  component: z.literal("ReviewLink"),
  label: z.string().min(1),
  concept: z.string().min(1),
});

const NextStepListSchema = z.object({
  id: ComponentIdSchema,
  component: z.literal("NextStepList"),
  title: z.string().min(1),
  steps: z.array(z.string().min(1)).min(1),
});

export const FeedbackComponentSchema = z.discriminatedUnion("component", [
  FeedbackCardSchema,
  ConceptChipSchema,
  ReviewLinkSchema,
  NextStepListSchema,
]);

export const FeedbackSurfaceArgsSchema = z.object({
  surfaceId: z.string().min(1),
  components: z
    .array(FeedbackComponentSchema)
    .min(1)
    .describe(
      `Flat component list. The FeedbackCard has id "${ROOT_COMPONENT_ID}" and lists every other id in children.`,
    ),
});

export type FeedbackComponent = z.infer<typeof FeedbackComponentSchema>;
export type FeedbackSurfaceArgs = z.infer<typeof FeedbackSurfaceArgsSchema>;
