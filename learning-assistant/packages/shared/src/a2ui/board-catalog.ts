import { CHAT_CATALOG } from "./chat-catalog";

/**
 * The dynamic Board catalog: what the Supervisor may compose with
 * `renderSurface` for the canvas. It is the chat catalog plus wider layout
 * and reading components the canvas already draws. The server validates the
 * tree against it, and the web app registers React components under the same
 * catalog id (`apps/web/features/canvas/constants/board-catalog.ts`).
 */
export const BOARD_CATALOG_ID = "learning-assistant/board/v1";

/** Prefix of every Board surface id; the server adds a unique suffix. */
export const BOARD_SURFACE_ID_PREFIX = "board-";

/** The Board keeps this many surfaces; the oldest is dropped first. */
export const MAX_BOARD_SURFACES = 8;

/** Where `renderSurface` draws: a card in the chat, or the canvas Board. */
export const SURFACE_TARGETS = ["chat", "canvas"] as const;

export const TILE_TONES = ["indigo", "emerald", "amber", "rose"] as const;

const STRING_LIST = { type: "array", items: { type: "string" } } as const;

const CHILD_IDS = {
  type: "array",
  items: { type: "string" },
  description: "Ids of the child components, in display order",
} as const;

export const BOARD_CATALOG = {
  catalogId: BOARD_CATALOG_ID,
  components: {
    ...CHAT_CATALOG.components,
    Stack: {
      type: "object",
      description: "Vertical stack with even spacing; the usual root.",
      properties: { children: CHILD_IDS },
      required: ["children"],
    },
    Columns: {
      type: "object",
      description:
        "Two or three children side by side on a wide canvas, stacked on a narrow one.",
      properties: { children: CHILD_IDS },
      required: ["children"],
    },
    ArticleCard: {
      type: "object",
      description: "A reading: eyebrow label, title and a body of prose.",
      properties: {
        eyebrow: { type: "string" },
        title: { type: "string" },
        body: { type: "string" },
      },
      required: ["title", "body"],
    },
    InsightCallout: {
      type: "object",
      description: "One highlighted key idea with a short label.",
      properties: { label: { type: "string" }, text: { type: "string" } },
      required: ["text"],
    },
    Flashcards: {
      type: "object",
      description: "Flip cards for key terms, one at a time.",
      properties: {
        title: { type: "string" },
        cards: {
          type: "array",
          items: {
            type: "object",
            properties: {
              term: { type: "string" },
              definition: { type: "string" },
            },
            required: ["term", "definition"],
          },
        },
      },
      required: ["cards"],
    },
    StatTiles: {
      type: "object",
      description: "A card of two to four headline numbers.",
      properties: {
        title: { type: "string" },
        tiles: {
          type: "array",
          items: {
            type: "object",
            properties: {
              label: { type: "string" },
              value: { type: "string" },
              tone: { type: "string", enum: [...TILE_TONES] },
            },
            required: ["label", "value", "tone"],
          },
        },
      },
      required: ["title", "tiles"],
    },
    CodeBlock: {
      type: "object",
      description:
        "A code snippet with line numbers and a Copy button; highlightLines marks the lines that matter.",
      properties: {
        language: { type: "string", description: 'e.g. "typescript"' },
        filename: { type: "string", description: 'e.g. "app.ts", or ""' },
        code: { type: "string" },
        highlightLines: {
          type: "array",
          items: { type: "number" },
          description: "1-based line numbers, or []",
        },
      },
      required: ["language", "filename", "code", "highlightLines"],
    },
    KeyValueList: {
      type: "object",
      description:
        "Labelled facts, one per row: a glossary, parameters, properties or settings.",
      properties: {
        title: { type: "string" },
        items: {
          type: "array",
          items: {
            type: "object",
            properties: { key: { type: "string" }, value: { type: "string" } },
            required: ["key", "value"],
          },
        },
      },
      required: ["title", "items"],
    },
    ProsCons: {
      type: "object",
      description: "Advantages and drawbacks of one choice, side by side.",
      properties: {
        prosTitle: { type: "string", description: 'e.g. "Pros"' },
        pros: STRING_LIST,
        consTitle: { type: "string", description: 'e.g. "Cons"' },
        cons: STRING_LIST,
      },
      required: ["prosTitle", "pros", "consTitle", "cons"],
    },
    Checklist: {
      type: "object",
      description:
        "Things to check off, e.g. a study plan or prerequisites; done items are ticked.",
      properties: {
        title: { type: "string" },
        items: {
          type: "array",
          items: {
            type: "object",
            properties: {
              text: { type: "string" },
              done: { type: "boolean" },
            },
            required: ["text", "done"],
          },
        },
      },
      required: ["title", "items"],
    },
  },
};

export type BoardComponentName = keyof typeof BOARD_CATALOG.components;
