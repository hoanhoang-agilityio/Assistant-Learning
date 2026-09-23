import { CHAT_MODES, VIEW_MODES } from "@repo/shared/schemas";

import {
  CANVAS_MIN_WIDTH,
  CHAT_WIDTH,
  COMPACT_MAX_WIDTH,
  DEFAULT_LAYOUT,
  DEVICE_WIDTHS,
} from "@/constants/layout";
import type { Display, Layout } from "@/types/layout";

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

const isOneOf = <T extends string>(
  values: readonly T[],
  value: unknown,
): value is T => values.includes(value as T);

/**
 * Reads the persisted layout; invalid fields fall back to the defaults. A
 * layout saved before chat modes existed keeps its collapsed chat.
 */
export const parseLayout = (raw: unknown): Layout => {
  const input: Partial<Record<keyof Layout | "isChatOpen", unknown>> =
    raw && typeof raw === "object" ? raw : {};
  const legacyChatMode = input.isChatOpen === false ? "hidden" : undefined;

  return {
    chatWidth:
      typeof input.chatWidth === "number"
        ? clampChatWidth(input.chatWidth)
        : DEFAULT_LAYOUT.chatWidth,
    chatMode: isOneOf(CHAT_MODES, input.chatMode)
      ? input.chatMode
      : (legacyChatMode ?? DEFAULT_LAYOUT.chatMode),
    viewMode: isOneOf(VIEW_MODES, input.viewMode)
      ? input.viewMode
      : DEFAULT_LAYOUT.viewMode,
  };
};

/**
 * Works out the layout on screen. `tablet` and `mobile` draw the page in a
 * device-width frame when the window is wider than the device; `desktop`
 * keeps the docked chat whatever the width. A docked chat that does not fit
 * beside the canvas is shown as a popup.
 */
export const resolveDisplay = (
  { chatMode, viewMode }: Layout,
  windowWidth: number,
): Display => {
  const deviceWidth =
    viewMode === "tablet" || viewMode === "mobile"
      ? DEVICE_WIDTHS[viewMode]
      : null;
  const frameWidth =
    deviceWidth !== null && deviceWidth < windowWidth ? deviceWidth : null;
  const width = frameWidth ?? windowWidth;
  const isCompact = viewMode !== "desktop" && width < COMPACT_MAX_WIDTH;

  return {
    frameWidth,
    width,
    isCompact,
    chat: isCompact && chatMode === "docked" ? "popup" : chatMode,
  };
};

/**
 * The `setLayout` tool result: what the student now sees, and why a docked
 * chat became a popup when it did.
 */
export const describeDisplay = (
  { chatMode, viewMode }: Layout,
  { frameWidth, width, chat }: Display,
): string => {
  const view =
    frameWidth === null
      ? `View ${viewMode}, ${width}px wide.`
      : `View ${viewMode}, previewed in a ${frameWidth}px frame.`;
  const docking =
    chatMode === chat
      ? `Chat ${chat}.`
      : `Chat ${chat}: the page is too narrow to dock it, so it shows as a popup.`;

  return `${view} ${docking}`;
};
