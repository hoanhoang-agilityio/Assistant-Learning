import { type Settings, SettingsSchema } from "@repo/shared/schemas";
import { z } from "zod";

import { SETTINGS_API_PATH } from "@/features/settings/constants/settings";

const SavedSettingsSchema = z.object({ settings: SettingsSchema.nullable() });

/** The settings saved to the user's account, or `null` before the first save. */
export const fetchSavedSettings = async (): Promise<Settings | null> => {
  const response = await fetch(SETTINGS_API_PATH);
  if (!response.ok) {
    throw new Error(`Loading settings failed (${response.status})`);
  }
  return SavedSettingsSchema.parse(await response.json()).settings;
};

export const saveSettings = async (settings: Settings): Promise<void> => {
  const response = await fetch(SETTINGS_API_PATH, {
    method: "PUT",
    headers: { "content-type": "application/json" },
    body: JSON.stringify(settings),
  });
  if (!response.ok) {
    throw new Error(`Saving settings failed (${response.status})`);
  }
};
