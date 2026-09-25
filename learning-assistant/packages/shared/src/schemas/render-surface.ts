import { z } from "zod";

import { SURFACE_TARGETS, TILE_TONES } from "../a2ui/board-catalog";
import { ROOT_COMPONENT_ID } from "../a2ui/canvas-catalog";
import { CALLOUT_TONES } from "../a2ui/chat-catalog";
import { BoardSurfaceSchema } from "./learning-state";

/**
 * The `renderSurface` arguments: a flat A2UI v0.9 component list with literal
 * values (no data bindings). The schema allows every Board component; the
 * server then checks the tree against the target's catalog, so a Board-only
 * component sent to the chat comes back as an error. It mirrors
 * `CHAT_CATALOG` and `BOARD_CATALOG`; every prop is required so strict tool
 * schemas accept it.
 */
const ComponentIdSchema = z
  .string()
  .min(1)
  .describe(`Unique id; the root's id is ${ROOT_COMPONENT_ID}`);

const ChildIdsSchema = z.array(z.string().min(1));

const PanelSchema = z.object({
  id: ComponentIdSchema,
  component: z.literal("Panel"),
  title: z.string().min(1),
  children: ChildIdsSchema,
});

const SectionSchema = z.object({
  id: ComponentIdSchema,
  component: z.literal("Section"),
  heading: z.string().min(1),
  children: ChildIdsSchema,
});

const ParagraphSchema = z.object({
  id: ComponentIdSchema,
  component: z.literal("Paragraph"),
  text: z.string().min(1),
});

const BulletListSchema = z.object({
  id: ComponentIdSchema,
  component: z.literal("BulletList"),
  items: z.array(z.string().min(1)).min(1),
  ordered: z.boolean(),
});

const CalloutSchema = z.object({
  id: ComponentIdSchema,
  component: z.literal("Callout"),
  tone: z.enum(CALLOUT_TONES),
  text: z.string().min(1),
});

const TableSchema = z.object({
  id: ComponentIdSchema,
  component: z.literal("Table"),
  columns: z.array(z.string().min(1)).min(2),
  rows: z.array(z.array(z.string())).min(1),
});

const TimelineSchema = z.object({
  id: ComponentIdSchema,
  component: z.literal("Timeline"),
  items: z
    .array(z.object({ label: z.string().min(1), detail: z.string().min(1) }))
    .min(2),
});

const MeterSchema = z.object({
  id: ComponentIdSchema,
  component: z.literal("Meter"),
  label: z.string().min(1),
  percent: z.number().min(0).max(100),
});

const TagListSchema = z.object({
  id: ComponentIdSchema,
  component: z.literal("TagList"),
  tags: z.array(z.string().min(1)).min(1),
});

const StackSchema = z.object({
  id: ComponentIdSchema,
  component: z.literal("Stack"),
  children: ChildIdsSchema,
});

const ColumnsSchema = z.object({
  id: ComponentIdSchema,
  component: z.literal("Columns"),
  children: ChildIdsSchema.describe("Two or three child ids"),
});

const ArticleCardSchema = z.object({
  id: ComponentIdSchema,
  component: z.literal("ArticleCard"),
  eyebrow: z.string(),
  title: z.string().min(1),
  body: z.string().min(1),
});

const InsightCalloutSchema = z.object({
  id: ComponentIdSchema,
  component: z.literal("InsightCallout"),
  label: z.string(),
  text: z.string().min(1),
});

const FlashcardsSchema = z.object({
  id: ComponentIdSchema,
  component: z.literal("Flashcards"),
  title: z.string(),
  cards: z
    .array(z.object({ term: z.string().min(1), definition: z.string().min(1) }))
    .min(1),
});

const StatTilesSchema = z.object({
  id: ComponentIdSchema,
  component: z.literal("StatTiles"),
  title: z.string().min(1),
  tiles: z
    .array(
      z.object({
        label: z.string().min(1),
        value: z.string().min(1),
        tone: z.enum(TILE_TONES),
      }),
    )
    .min(2)
    .max(4),
});

const CodeBlockSchema = z.object({
  id: ComponentIdSchema,
  component: z.literal("CodeBlock"),
  language: z.string().min(1),
  filename: z.string().describe('A file name, or "" for none'),
  code: z
    .string()
    .min(1)
    .describe("The code exactly as it should read; at most about 40 lines"),
  highlightLines: z
    .array(z.int().min(1))
    .describe("1-based lines to highlight, or [] for none"),
});

const KeyValueListSchema = z.object({
  id: ComponentIdSchema,
  component: z.literal("KeyValueList"),
  title: z.string(),
  items: z
    .array(z.object({ key: z.string().min(1), value: z.string().min(1) }))
    .min(1),
});

const ProsConsSchema = z.object({
  id: ComponentIdSchema,
  component: z.literal("ProsCons"),
  prosTitle: z.string().min(1),
  pros: z.array(z.string().min(1)).min(1),
  consTitle: z.string().min(1),
  cons: z.array(z.string().min(1)).min(1),
});

const ChecklistSchema = z.object({
  id: ComponentIdSchema,
  component: z.literal("Checklist"),
  title: z.string(),
  items: z
    .array(z.object({ text: z.string().min(1), done: z.boolean() }))
    .min(1),
});

export const SurfaceComponentSchema = z.discriminatedUnion("component", [
  PanelSchema,
  SectionSchema,
  ParagraphSchema,
  BulletListSchema,
  CalloutSchema,
  TableSchema,
  TimelineSchema,
  MeterSchema,
  TagListSchema,
  StackSchema,
  ColumnsSchema,
  ArticleCardSchema,
  InsightCalloutSchema,
  FlashcardsSchema,
  StatTilesSchema,
  CodeBlockSchema,
  KeyValueListSchema,
  ProsConsSchema,
  ChecklistSchema,
]);

export const SurfaceTargetSchema = z.enum(SURFACE_TARGETS);

export const RenderSurfaceArgsSchema = z.object({
  target: SurfaceTargetSchema.describe(
    "chat: a compact card in the reply; canvas: a wide view on the Board that stays",
  ),
  title: z
    .string()
    .min(1)
    .describe("Short name for the view; the Board lists views by it"),
  components: z
    .array(SurfaceComponentSchema)
    .min(1)
    .describe(
      `Flat component list with one root, id "${ROOT_COMPONENT_ID}"; each other component is listed in exactly one parent's children.`,
    ),
});

const SurfaceIdSchema = z
  .string()
  .min(1)
  .describe('A Board view\'s id from "board" in "Application State"');

/** `readBoardSurface` arguments. */
export const ReadBoardSurfaceArgsSchema = z.object({
  surfaceId: SurfaceIdSchema,
});

/** `updateBoardSurface` arguments: the view's whole revised component list. */
export const UpdateBoardSurfaceArgsSchema = z.object({
  surfaceId: SurfaceIdSchema,
  title: z
    .string()
    .min(1)
    .describe("The view's title; keep it unless the student renamed it"),
  components: z
    .array(SurfaceComponentSchema)
    .min(1)
    .describe(
      `The whole revised list, not just the changes. Keep the ids of components that stay; the root is "${ROOT_COMPONENT_ID}".`,
    ),
});

/** `deleteBoardSurface` arguments. */
export const DeleteBoardSurfaceArgsSchema = z.object({
  surfaceIds: z
    .array(z.string().min(1))
    .describe(
      'Ids of the Board views to remove, from "board" in "Application State"; every id to clear the Board',
    ),
});

/** A `deleteBoardSurface` result: the views taken off the Board. */
export const BoardRemovalResultSchema = z.object({
  removed: z
    .array(z.object({ id: z.string().min(1), title: z.string() }))
    .min(1),
});

/**
 * A `renderSurface` (canvas) or `updateBoardSurface` result: the new Board
 * view. A chat result is an `a2ui_operations` envelope instead, which the
 * A2UI middleware draws.
 */
export const BoardSurfaceResultSchema = z.object({
  surface: BoardSurfaceSchema,
});

export type SurfaceComponent = z.infer<typeof SurfaceComponentSchema>;
export type DeleteBoardSurfaceArgs = z.infer<
  typeof DeleteBoardSurfaceArgsSchema
>;
export type BoardRemovalResult = z.infer<typeof BoardRemovalResultSchema>;
export type ReadBoardSurfaceArgs = z.infer<typeof ReadBoardSurfaceArgsSchema>;
export type UpdateBoardSurfaceArgs = z.infer<
  typeof UpdateBoardSurfaceArgsSchema
>;
export type SurfaceTarget = z.infer<typeof SurfaceTargetSchema>;
export type RenderSurfaceArgs = z.infer<typeof RenderSurfaceArgsSchema>;
