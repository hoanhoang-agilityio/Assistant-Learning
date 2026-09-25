/**
 * The dynamic chat catalog: the only components the Supervisor may compose
 * with `renderSurface` for the chat. The server validates the tree against it,
 * and the web app registers React components under the same catalog id
 * (`apps/web/features/chat/constants/chat-catalog.ts`).
 */
export const CHAT_CATALOG_ID = "learning-assistant/chat/v1";

/** Prefix of every chat surface id; the server adds a unique suffix. */
export const CHAT_SURFACE_ID_PREFIX = "chat-";

export const CALLOUT_TONES = ["info", "tip", "warning"] as const;

const CHILD_IDS = {
  type: "array",
  items: { type: "string" },
  description: "Ids of the child components, in display order",
} as const;

const STRING_LIST = { type: "array", items: { type: "string" } } as const;

export const CHAT_CATALOG = {
  catalogId: CHAT_CATALOG_ID,
  components: {
    Panel: {
      type: "object",
      description:
        'The card around the whole surface. Exactly one, with id "root"; every other component is its child or a Section\'s child.',
      properties: {
        title: { type: "string", description: "Short headline" },
        children: CHILD_IDS,
      },
      required: ["title", "children"],
    },
    Section: {
      type: "object",
      description: "A headed group of components inside the Panel.",
      properties: { heading: { type: "string" }, children: CHILD_IDS },
      required: ["heading", "children"],
    },
    Paragraph: {
      type: "object",
      description: "One to three sentences of plain text.",
      properties: { text: { type: "string" } },
      required: ["text"],
    },
    BulletList: {
      type: "object",
      description: "Short points; ordered for a sequence.",
      properties: { items: STRING_LIST, ordered: { type: "boolean" } },
      required: ["items", "ordered"],
    },
    Callout: {
      type: "object",
      description: "One highlighted sentence: an info, a tip or a warning.",
      properties: {
        tone: { type: "string", enum: [...CALLOUT_TONES] },
        text: { type: "string" },
      },
      required: ["tone", "text"],
    },
    Table: {
      type: "object",
      description: "A small table; every row has one cell per column.",
      properties: {
        columns: STRING_LIST,
        rows: { type: "array", items: STRING_LIST },
      },
      required: ["columns", "rows"],
    },
    Timeline: {
      type: "object",
      description: "Dated or ordered events, each a label and a detail.",
      properties: {
        items: {
          type: "array",
          items: {
            type: "object",
            properties: {
              label: { type: "string" },
              detail: { type: "string" },
            },
            required: ["label", "detail"],
          },
        },
      },
      required: ["items"],
    },
    Meter: {
      type: "object",
      description: "A labelled bar from 0 to 100, e.g. difficulty or usage.",
      properties: {
        label: { type: "string" },
        percent: { type: "number", minimum: 0, maximum: 100 },
      },
      required: ["label", "percent"],
    },
    TagList: {
      type: "object",
      description: "Keywords or related terms as small tags.",
      properties: { tags: STRING_LIST },
      required: ["tags"],
    },
  },
};

export type ChatComponentName = keyof typeof CHAT_CATALOG.components;
