import { DEFAULT_SETTINGS } from "@repo/shared/constants/settings";
import { type Settings, SettingsSchema } from "@repo/shared/schemas";
import { z } from "zod";

import { type AppContextEntry, AppContextEntrySchema } from "../schemas/graph";
import { dropA2UIContext } from "./agent-context";

const AppContextSchema = z.array(AppContextEntrySchema);

/** The settings the browser sent with a run. Invalid input falls back to the defaults. */
export const readRunSettings = (raw: unknown): Settings => {
  const parsed = SettingsSchema.safeParse(raw);
  return parsed.success ? parsed.data : DEFAULT_SETTINGS;
};

/**
 * The `useAgentContext` entries the browser sent with a run, without
 * CopilotKit's A2UI entries. Anything that is not a list of entries is
 * treated as none.
 */
export const readAppContext = (raw: unknown): AppContextEntry[] => {
  const parsed = AppContextSchema.safeParse(raw);
  return parsed.success ? dropA2UIContext(parsed.data) : [];
};
