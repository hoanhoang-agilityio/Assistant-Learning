import type { BoardSurface } from "@repo/shared/schemas";

const isRecord = (value: unknown): value is Record<string, unknown> =>
  typeof value === "object" && value !== null && !Array.isArray(value);

/**
 * The component list a Board view was drawn with: the `components` of its
 * `updateComponents` operation, or `null` if it has none.
 */
export const getSurfaceComponents = ({
  operations,
}: BoardSurface): Record<string, unknown>[] | null => {
  for (const operation of operations) {
    const update = isRecord(operation) ? operation.updateComponents : null;
    if (isRecord(update) && Array.isArray(update.components)) {
      return update.components.filter(isRecord);
    }
  }
  return null;
};
