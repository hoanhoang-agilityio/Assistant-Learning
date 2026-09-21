import {
  type CatalogDefinitions,
  createCatalog,
} from "@copilotkit/a2ui-renderer";
import { CANVAS_CATALOG_ID } from "@repo/shared/a2ui/canvas-catalog";
// The A2UI renderer and its binder use zod 3 (the binder reads
// `_def.typeName` to find data bindings), so component props are declared
// with the same zod 3 package (`zod3` = `zod@3.25.76`).
// TODO: switch to zod 4 when the binder is updated.
import { z } from "zod3";

import { ArticleCard } from "@/features/canvas/components/a2ui/ArticleCard";
import { Flashcards } from "@/features/canvas/components/a2ui/Flashcards";
import { InsightCallout } from "@/features/canvas/components/a2ui/InsightCallout";
import { QuestionCard } from "@/features/canvas/components/a2ui/QuestionCard";
import { QuizActionBar } from "@/features/canvas/components/a2ui/QuizActionBar";
import { SourceList } from "@/features/canvas/components/a2ui/SourceList";
import { Stack } from "@/features/canvas/components/a2ui/Stack";

/** `{ "path": "/…" }`: a JSON Pointer into the surface's data model. */
const BindingSchema = z.object({ path: z.string() });

/** A literal string or a binding to one. */
const TextSchema = z.union([z.string(), BindingSchema]);

const NumberSchema = z.union([z.number(), BindingSchema]);

const BooleanSchema = z.union([z.boolean(), BindingSchema]);

/**
 * Static child ids, or a template: one `componentId` per item of the array at
 * `path`. The binder expands a template into `{ id, basePath }` children.
 */
const ChildListSchema = z.union([
  z.array(z.string()),
  z.object({ componentId: z.string(), path: z.string() }),
]);

/**
 * An A2UI action. The binder recognises the `{ event }` shape and hands the
 * component a function that dispatches it with its context resolved.
 */
const ActionSchema = z.union([
  z.object({
    event: z.object({
      name: z.string(),
      context: z.record(z.unknown()).optional(),
    }),
  }),
  z.object({ functionCall: z.unknown() }),
]);

const QuestionResultSchema = z.union([
  z.object({
    correctIndex: z.number(),
    isCorrect: z.boolean(),
    explanation: z.string(),
  }),
  BindingSchema,
]);

const KeyTermListSchema = z.union([
  z.array(z.object({ term: z.string(), definition: z.string() })),
  BindingSchema,
]);

const SourceListSchema = z.union([
  z.array(z.object({ title: z.string(), url: z.string() })),
  BindingSchema,
]);

/** The learning components, on top of the basic catalog. */
export const CANVAS_COMPONENT_DEFINITIONS = {
  Stack: {
    description:
      "Vertical stack of cards with even spacing. Use as the root, or repeat one component over a list.",
    props: z.object({ children: ChildListSchema }),
  },
  ArticleCard: {
    description: "A reading: eyebrow label, title and body, plus one child.",
    props: z.object({
      eyebrow: TextSchema.optional(),
      title: TextSchema,
      body: TextSchema,
      child: z.string().optional(),
    }),
  },
  InsightCallout: {
    description: "A highlighted key idea.",
    props: z.object({ label: TextSchema.optional(), text: TextSchema }),
  },
  Flashcards: {
    description: "Flip cards for key terms, one at a time.",
    props: z.object({ title: TextSchema.optional(), cards: KeyTermListSchema }),
  },
  SourceList: {
    description: "Cited sources as links.",
    props: z.object({
      title: TextSchema.optional(),
      sources: SourceListSchema,
      emptyText: TextSchema.optional(),
    }),
  },
  QuestionCard: {
    description:
      "One multiple-choice question: pick an option; after grading, shows the correct option and why.",
    props: z.object({
      questionId: TextSchema,
      number: NumberSchema,
      concept: TextSchema.optional(),
      question: TextSchema,
      options: z.union([z.array(z.string()), BindingSchema]),
      selectedIndex: NumberSchema.optional(),
      result: QuestionResultSchema.optional(),
      isLocked: BooleanSchema.optional(),
    }),
  },
  QuizActionBar: {
    description: "Quiz progress with Submit, Retake and New questions.",
    props: z.object({
      answeredCount: NumberSchema,
      total: NumberSchema,
      canSubmit: BooleanSchema,
      isSubmitted: BooleanSchema,
      isLocked: BooleanSchema.optional(),
      submitAction: ActionSchema,
      retakeAction: ActionSchema,
      newQuestionsAction: ActionSchema,
    }),
  },
} satisfies CatalogDefinitions;

/** The catalog every fixed canvas surface renders with. */
export const CANVAS_CATALOG = createCatalog(
  CANVAS_COMPONENT_DEFINITIONS,
  {
    Stack,
    ArticleCard,
    InsightCallout,
    Flashcards,
    SourceList,
    QuestionCard,
    QuizActionBar,
  },
  { catalogId: CANVAS_CATALOG_ID, includeBasicCatalog: true },
);
