/**
 * The dynamic Feedback catalog: the only components the Evaluator may compose
 * with `render_a2ui`. The web app registers React components under the same
 * catalog id (`extendsBasicCatalog`). First version; M5.3 refines the props.
 */
export const FEEDBACK_CATALOG_ID = "learning-assistant/feedback/v1";

export const FEEDBACK_CATALOG = {
  catalogId: FEEDBACK_CATALOG_ID,
  components: {
    FeedbackCard: {
      type: "object",
      description: "Card with the overall feedback. Use it as the root.",
      properties: {
        title: { type: "string" },
        body: { type: "string", description: "Markdown feedback text" },
        children: {
          type: "array",
          items: { type: "string" },
          description: "Ids of ConceptChip, ReviewLink and NextStepList",
        },
      },
      required: ["title", "body"],
    },
    ConceptChip: {
      type: "object",
      description: "A concept with the student's mastery of it.",
      properties: {
        concept: { type: "string" },
        percent: { type: "number", minimum: 0, maximum: 100 },
        isWeakest: { type: "boolean" },
      },
      required: ["concept", "percent"],
    },
    ReviewLink: {
      type: "object",
      description: "Points the student to a part of the notes to review.",
      properties: {
        label: { type: "string" },
        concept: { type: "string" },
      },
      required: ["label", "concept"],
    },
    NextStepList: {
      type: "object",
      description: "Ordered list of suggested next steps.",
      properties: {
        steps: { type: "array", items: { type: "string" }, minItems: 1 },
      },
      required: ["steps"],
    },
  },
};
