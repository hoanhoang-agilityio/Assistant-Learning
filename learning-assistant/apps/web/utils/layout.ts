import {
  CANVAS_MIN_WIDTH,
  CHAT_WIDTH,
  DEFAULT_LAYOUT,
} from "@/constants/layout";
import type { Layout } from "@/types/layout";

/**
 * Clamps the chat width to its limits and, when the container width is known,
 * leaves at least `CANVAS_MIN_WIDTH` for the canvas.
 */
export const clampChatWidth = (
  width: number,
  containerWidth?: number,
): number => {
  if (!Number.isFinite(width)) {
    return CHAT_WIDTH.default;
  }
  const roomLeft =
    containerWidth === undefined
      ? CHAT_WIDTH.max
      : containerWidth - CANVAS_MIN_WIDTH;
  const max = Math.max(CHAT_WIDTH.min, Math.min(CHAT_WIDTH.max, roomLeft));
  return Math.round(Math.min(max, Math.max(CHAT_WIDTH.min, width)));
};

/** Reads the persisted layout; invalid fields fall back to the defaults. */
export const parseLayout = (raw: unknown): Layout => {
  const input: Partial<Record<keyof Layout, unknown>> =
    raw && typeof raw === "object" ? raw : {};
  return {
    chatWidth:
      typeof input.chatWidth === "number"
        ? clampChatWidth(input.chatWidth)
        : DEFAULT_LAYOUT.chatWidth,
    isChatOpen:
      typeof input.isChatOpen === "boolean"
        ? input.isChatOpen
        : DEFAULT_LAYOUT.isChatOpen,
  };
};
