import { TierSchema } from "@repo/shared/schemas";
import { z } from "zod";

import type {
  ChildRef,
  MasteryItem,
  QuestionResult,
  StatChip,
  StatTile,
} from "@/features/canvas/types/a2ui";

const ToneSchema = z.enum(["indigo", "emerald", "amber", "rose"]);

const StatTileSchema = z.object({
  label: z.string(),
  value: z.string(),
  tone: ToneSchema,
});

const MasteryItemSchema = z.object({
  concept: z.string(),
  percent: z.number().min(0).max(100),
  tone: ToneSchema,
  isWeakest: z.boolean(),
});

const StatChipSchema = z.object({ label: z.string(), value: z.string() });

/** The items of a bound list that have the expected shape; others are dropped. */
const readItems = <T>(value: unknown, schema: z.ZodType<T>): T[] =>
  Array.isArray(value)
    ? value.flatMap((item: unknown) => {
        const parsed = schema.safeParse(item);
        return parsed.success ? [parsed.data] : [];
      })
    : [];

/**
 * The binder resolves `{ path }` bindings before a component renders, but the
 * catalog's prop types still include the unresolved binding. These narrow a
 * resolved prop to what the component draws, with an empty fallback.
 */
export const readText = (value: unknown): string =>
  typeof value === "string" ? value : "";

export const readList = <T>(value: readonly T[] | object | undefined): T[] =>
  Array.isArray(value) ? value : [];

export const readNumber = (value: unknown): number | null =>
  typeof value === "number" ? value : null;

export const readBoolean = (value: unknown): boolean => value === true;

const isChildRef = (item: unknown): item is ChildRef =>
  typeof item === "object" &&
  item !== null &&
  "id" in item &&
  typeof item.id === "string";

/**
 * A child list: static ids (`["a", "b"]`), or a template the binder expanded
 * into one `{ id, basePath }` per item of the bound array.
 */
export const readChildren = (value: unknown): ChildRef[] =>
  Array.isArray(value)
    ? value.flatMap((item: unknown) => {
        if (typeof item === "string") {
          return [{ id: item }];
        }
        return isChildRef(item) ? [item] : [];
      })
    : [];

/**
 * An action prop. The binder turns `{ event: … }` into a function that
 * dispatches it with its context bindings resolved.
 */
export const readAction = (value: unknown): (() => void) | undefined =>
  typeof value === "function"
    ? () => {
        value();
      }
    : undefined;

export const readQuestionResult = (value: unknown): QuestionResult | null => {
  if (typeof value !== "object" || value === null) {
    return null;
  }
  const { correctIndex, isCorrect, explanation } = value as Record<
    string,
    unknown
  >;
  return typeof correctIndex === "number" && typeof isCorrect === "boolean"
    ? { correctIndex, isCorrect, explanation: readText(explanation) }
    : null;
};

export const readStatTiles = (value: unknown): StatTile[] =>
  readItems(value, StatTileSchema);

export const readMasteryItems = (value: unknown): MasteryItem[] =>
  readItems(value, MasteryItemSchema);

export const readStatChips = (value: unknown): StatChip[] =>
  readItems(value, StatChipSchema);

/** A tier name, or `null` when the value is not one. */
export const readTier = (value: unknown) => {
  const parsed = TierSchema.safeParse(value);
  return parsed.success ? parsed.data : null;
};
