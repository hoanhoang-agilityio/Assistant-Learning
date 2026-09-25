import { ROOT_COMPONENT_ID } from "@repo/shared/a2ui/canvas-catalog";
import type { z } from "zod";

/** A catalog component as far as drawing a draft is concerned. */
interface DraftComponent {
  id: string;
  children?: string[];
}

/**
 * The components of a partial `components` argument that can be drawn: each
 * one complete enough to pass `schema` (the one being written may already
 * pass, so its text grows as it streams), the first of each id, and children
 * that point only at components already written. `null` until the root is
 * written, since nothing can be drawn without it.
 */
export const toDraftComponents = <T extends DraftComponent>(
  raw: unknown,
  schema: z.ZodType<T>,
): T[] | null => {
  if (!Array.isArray(raw)) {
    return null;
  }
  const byId = new Map<string, T>();
  for (const item of raw) {
    const parsed = schema.safeParse(item);
    if (parsed.success && !byId.has(parsed.data.id)) {
      byId.set(parsed.data.id, parsed.data);
    }
  }
  if (!byId.has(ROOT_COMPONENT_ID)) {
    return null;
  }
  return [...byId.values()].map((component) =>
    component.children
      ? {
          ...component,
          children: component.children.filter((id) => byId.has(id)),
        }
      : component,
  );
};
