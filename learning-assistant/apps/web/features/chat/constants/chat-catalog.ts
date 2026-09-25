import {
  type CatalogDefinitions,
  createCatalog,
} from "@copilotkit/a2ui-renderer";
import { CALLOUT_TONES, CHAT_CATALOG_ID } from "@repo/shared/a2ui/chat-catalog";
// zod 3 for the renderer's binder; see `canvas/constants/a2ui-catalog.ts`.
import { z } from "zod3";

import { BulletList } from "@/features/chat/components/a2ui/BulletList";
import { Callout } from "@/features/chat/components/a2ui/Callout";
import { Meter } from "@/features/chat/components/a2ui/Meter";
import { Panel } from "@/features/chat/components/a2ui/Panel";
import { Paragraph } from "@/features/chat/components/a2ui/Paragraph";
import { Section } from "@/features/chat/components/a2ui/Section";
import { Table } from "@/features/chat/components/a2ui/Table";
import { TagList } from "@/features/chat/components/a2ui/TagList";
import { Timeline } from "@/features/chat/components/a2ui/Timeline";

/**
 * The components the Supervisor composes chat surfaces from. The server only
 * accepts these (`@repo/shared/a2ui/chat-catalog`); the props here match it.
 */
export const CHAT_COMPONENT_DEFINITIONS = {
  Panel: {
    description: "The card around the surface: a title and its children.",
    props: z.object({ title: z.string(), children: z.array(z.string()) }),
  },
  Section: {
    description: "A headed group of components.",
    props: z.object({ heading: z.string(), children: z.array(z.string()) }),
  },
  Paragraph: {
    description: "Plain text.",
    props: z.object({ text: z.string() }),
  },
  BulletList: {
    description: "Short points, numbered when ordered.",
    props: z.object({ items: z.array(z.string()), ordered: z.boolean() }),
  },
  Callout: {
    description: "A highlighted info, tip or warning.",
    props: z.object({ tone: z.enum(CALLOUT_TONES), text: z.string() }),
  },
  Table: {
    description: "A small table.",
    props: z.object({
      columns: z.array(z.string()),
      rows: z.array(z.array(z.string())),
    }),
  },
  Timeline: {
    description: "Ordered events.",
    props: z.object({
      items: z.array(z.object({ label: z.string(), detail: z.string() })),
    }),
  },
  Meter: {
    description: "A labelled bar from 0 to 100.",
    props: z.object({ label: z.string(), percent: z.number() }),
  },
  TagList: {
    description: "Small tags.",
    props: z.object({ tags: z.array(z.string()) }),
  },
} satisfies CatalogDefinitions;

/**
 * The catalog the chat's built-in A2UI renderer draws chat `renderSurface`
 * surfaces with; passed to `CopilotKitProvider` as `a2ui.catalog`.
 */
export const CHAT_UI_CATALOG = createCatalog(
  CHAT_COMPONENT_DEFINITIONS,
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
  },
  { catalogId: CHAT_CATALOG_ID },
);
