/**
 * The dynamic Feedback catalog: the only components the Evaluator may compose
 * with `render_a2ui`. The server validates the Evaluator's components against
 * it, and the web app registers React components under the same catalog id
 * (`apps/web/features/canvas/constants/feedback-catalog.ts`).
 */
export const FEEDBACK_CATALOG_ID = "learning-assistant/feedback/v1";

/** The one surface the Feedback stage renders; the server sets this id. */
export const FEEDBACK_SURFACE_ID = "feedback";

/**
 * A2UI actions on the Feedback surface, handled on the client. A ReviewLink
 * sends `review_concept` with `{ concept }` and the canvas opens the notes.
 */
export const FEEDBACK_ACTIONS = {
  reviewConcept: "review_concept",
} as const;

/** Mastery percent, a whole number from 0 to 100. */
const PERCENT = { type: "number", minimum: 0, maximum: 100 } as const;

export const FEEDBACK_CATALOG = {
  catalogId: FEEDBACK_CATALOG_ID,
  components: {
    FeedbackCard: {
      type: "object",
      description:
        'Card with the overall feedback. Exactly one, with id "root"; every other component is one of its children.',
      properties: {
        title: { type: "string", description: "Short, encouraging headline" },
        body: {
          type: "string",
          description:
            "Two to four sentences of plain-text feedback: what went well, what to work on",
        },
        children: {
          type: "array",
          items: { type: "string" },
          description:
            "Ids of the ConceptChip, ReviewLink and NextStepList components, in display order",
        },
      },
      required: ["title", "body", "children"],
    },
    ConceptChip: {
      type: "object",
      description:
        "One concept from the quiz with the student's mastery of it.",
      properties: {
        concept: { type: "string", description: "The concept name, exactly" },
        percent: PERCENT,
        isWeakest: {
          type: "boolean",
          description: "True only for the weakest concept",
        },
      },
      required: ["concept", "percent"],
    },
    ReviewLink: {
      type: "object",
      description:
        "Points the student to the part of their notes about one concept to review.",
      properties: {
        label: { type: "string", description: 'e.g. "Review closures"' },
        concept: { type: "string", description: "The concept name, exactly" },
      },
      required: ["label", "concept"],
    },
    NextStepList: {
      type: "object",
      description: "Ordered list of two to four concrete next steps.",
      properties: {
        title: { type: "string" },
        steps: { type: "array", items: { type: "string" }, minItems: 1 },
      },
      required: ["steps"],
    },
  },
};

export type FeedbackComponentName = keyof typeof FEEDBACK_CATALOG.components;
