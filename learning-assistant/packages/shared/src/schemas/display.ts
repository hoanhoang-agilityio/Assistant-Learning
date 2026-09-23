import { z } from "zod";

import { ThemeSchema } from "./settings";

/**
 * How the chat is shown: `docked` beside the canvas, `popup` as a floating
 * window over it, or `hidden` behind a slim rail.
 */
export const CHAT_MODES = ["docked", "popup", "hidden"] as const;

/**
 * The layout the page uses. `auto` follows the window width; `tablet` and
 * `mobile` preview that layout in a device-width frame on a wider screen.
 */
export const VIEW_MODES = ["auto", "desktop", "tablet", "mobile"] as const;

export const ChatModeSchema = z.enum(CHAT_MODES);
export const ViewModeSchema = z.enum(VIEW_MODES);

/** Arguments of the `setTheme` frontend tool. */
export const SetThemeParamsSchema = z.object({
  theme: ThemeSchema.describe(
    "system follows the device's light/dark preference",
  ),
});

/** Arguments of the `setLayout` frontend tool. Send only what changes. */
export const SetLayoutParamsSchema = z
  .object({
    chat: ChatModeSchema.optional().describe(
      "docked beside the canvas, popup floating over it, or hidden",
    ),
    view: ViewModeSchema.optional().describe(
      "auto follows the window; tablet and mobile preview that layout",
    ),
  })
  .refine((params) => params.chat !== undefined || params.view !== undefined, {
    message: "Send chat, view or both",
  });

export type ChatMode = z.infer<typeof ChatModeSchema>;
export type ViewMode = z.infer<typeof ViewModeSchema>;
export type SetThemeParams = z.infer<typeof SetThemeParamsSchema>;
export type SetLayoutParams = z.infer<typeof SetLayoutParamsSchema>;
