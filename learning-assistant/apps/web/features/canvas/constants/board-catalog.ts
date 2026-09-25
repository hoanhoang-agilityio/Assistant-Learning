import {
  type CatalogDefinitions,
  createCatalog,
} from "@copilotkit/a2ui-renderer";
import { BOARD_CATALOG_ID } from "@repo/shared/a2ui/board-catalog";
// zod 3 for the renderer's binder; see `a2ui-catalog.ts`.
import { z } from "zod3";

import { ArticleCard } from "@/features/canvas/components/a2ui/ArticleCard";
import { Checklist } from "@/features/canvas/components/a2ui/Checklist";
import { CodeBlock } from "@/features/canvas/components/a2ui/CodeBlock";
import { Columns } from "@/features/canvas/components/a2ui/Columns";
import { Flashcards } from "@/features/canvas/components/a2ui/Flashcards";
import { InsightCallout } from "@/features/canvas/components/a2ui/InsightCallout";
import { KeyValueList } from "@/features/canvas/components/a2ui/KeyValueList";
import { ProsCons } from "@/features/canvas/components/a2ui/ProsCons";
import { Stack } from "@/features/canvas/components/a2ui/Stack";
import { StatTiles } from "@/features/canvas/components/a2ui/StatTiles";
import { CANVAS_COMPONENT_DEFINITIONS } from "@/features/canvas/constants/a2ui-catalog";
import { BulletList } from "@/features/chat/components/a2ui/BulletList";
import { Callout } from "@/features/chat/components/a2ui/Callout";
import { Meter } from "@/features/chat/components/a2ui/Meter";
import { Panel } from "@/features/chat/components/a2ui/Panel";
import { Paragraph } from "@/features/chat/components/a2ui/Paragraph";
import { Section } from "@/features/chat/components/a2ui/Section";
import { Table } from "@/features/chat/components/a2ui/Table";
import { TagList } from "@/features/chat/components/a2ui/TagList";
import { Timeline } from "@/features/chat/components/a2ui/Timeline";
import { CHAT_COMPONENT_DEFINITIONS } from "@/features/chat/constants/chat-catalog";

/**
 * The components the Supervisor composes Board views from: the chat
 * components, the canvas's reading components (same props, so the same
 * renderers), and the Board's own: Columns, CodeBlock, KeyValueList,
 * ProsCons and Checklist. The server only accepts these
 * (`@repo/shared/a2ui/board-catalog`).
 */
export const BOARD_COMPONENT_DEFINITIONS = {
  ...CHAT_COMPONENT_DEFINITIONS,
  Stack: CANVAS_COMPONENT_DEFINITIONS.Stack,
  ArticleCard: CANVAS_COMPONENT_DEFINITIONS.ArticleCard,
  InsightCallout: CANVAS_COMPONENT_DEFINITIONS.InsightCallout,
  Flashcards: CANVAS_COMPONENT_DEFINITIONS.Flashcards,
  StatTiles: CANVAS_COMPONENT_DEFINITIONS.StatTiles,
  Columns: {
    description: "Two or three children side by side.",
    props: z.object({ children: z.array(z.string()) }),
  },
  CodeBlock: {
    description: "A code snippet with line numbers, highlights and Copy.",
    props: z.object({
      language: z.string(),
      filename: z.string(),
      code: z.string(),
      highlightLines: z.array(z.number()),
    }),
  },
  KeyValueList: {
    description: "Labelled facts, one per row.",
    props: z.object({
      title: z.string(),
      items: z.array(z.object({ key: z.string(), value: z.string() })),
    }),
  },
  ProsCons: {
    description: "Advantages and drawbacks side by side.",
    props: z.object({
      prosTitle: z.string(),
      pros: z.array(z.string()),
      consTitle: z.string(),
      cons: z.array(z.string()),
    }),
  },
  Checklist: {
    description: "Items with the done ones ticked.",
    props: z.object({
      title: z.string(),
      items: z.array(z.object({ text: z.string(), done: z.boolean() })),
    }),
  },
} satisfies CatalogDefinitions;

/** The catalog every Board view renders with. */
export const BOARD_UI_CATALOG = createCatalog(
  BOARD_COMPONENT_DEFINITIONS,
  {
    Panel,
    Section,
    Paragraph,
    BulletList,
    Callout,
    Table,
    Timeline,
    Meter,
    TagList,
    Stack,
    ArticleCard,
    InsightCallout,
    Flashcards,
    StatTiles,
    Columns,
    CodeBlock,
    KeyValueList,
    ProsCons,
    Checklist,
  },
  { catalogId: BOARD_CATALOG_ID },
);
