import {
  A2UI_VERSION,
  SURFACE_OPERATION_KEYS,
} from "@/features/canvas/constants/a2ui";
import type { A2UIMessage } from "@/features/canvas/types/a2ui";

const isRecord = (value: unknown): value is Record<string, unknown> =>
  typeof value === "object" && value !== null && !Array.isArray(value);

/** One operation for `surfaceId`: v0.9, exactly one known kind. */
const isSurfaceOperation = (
  value: unknown,
  surfaceId: string,
): value is A2UIMessage => {
  if (!isRecord(value) || value.version !== A2UI_VERSION) {
    return false;
  }
  const kinds = SURFACE_OPERATION_KEYS.filter((key) => key in value);
  if (kinds.length !== 1 || !kinds[0]) {
    return false;
  }
  const body = value[kinds[0]];
  return isRecord(body) && body.surfaceId === surfaceId;
};

/**
 * Stored operations (a Feedback or Board surface) that are safe to hand the
 * renderer. Empty unless they start by creating `surfaceId` and every one of
 * them targets it, so the caller shows its fallback instead.
 */
export const parseSurfaceOperations = (
  operations: readonly unknown[],
  surfaceId: string,
): A2UIMessage[] => {
  const [first] = operations;
  const isValid =
    operations.length > 0 &&
    operations.every((operation) => isSurfaceOperation(operation, surfaceId)) &&
    isRecord(first) &&
    "createSurface" in first;
  return isValid ? (operations as A2UIMessage[]) : [];
};
