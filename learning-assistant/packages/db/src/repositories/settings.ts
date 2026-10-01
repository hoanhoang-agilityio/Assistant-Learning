import type { Settings } from "@repo/shared/schemas";
import { eq } from "drizzle-orm";

import type { Database } from "../client";
import { userSettings } from "../schema";

/** The user's saved settings, or `null` before they first save any. */
export const getUserSettings = async (
  db: Database,
  userId: string,
): Promise<Settings | null> => {
  const [row] = await db
    .select({
      questionCount: userSettings.questionCount,
      learningLevel: userSettings.learningLevel,
      theme: userSettings.theme,
    })
    .from(userSettings)
    .where(eq(userSettings.userId, userId));
  return row ?? null;
};

export const saveUserSettings = async (
  db: Database,
  userId: string,
  settings: Settings,
  now = new Date(),
): Promise<void> => {
  await db
    .insert(userSettings)
    .values({ userId, ...settings, updatedAt: now })
    .onConflictDoUpdate({
      target: userSettings.userId,
      set: { ...settings, updatedAt: now },
    });
};
