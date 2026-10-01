import { getDatabase, getUserSettings, saveUserSettings } from "@repo/db";
import { SettingsSchema } from "@repo/shared/schemas";

import {
  INVALID_SETTINGS_ERROR,
  INVALID_SETTINGS_STATUS,
} from "@/features/settings/constants/settings";
import {
  createTooManyRequestsResponse,
  writeRateLimiter,
} from "@/services/rate-limit";
import { getUserRowId } from "@/services/users";

/** `GET /api/settings`: the saved settings, or `null` before the first save. */
export const getSettingsHandler = async (
  _request: Request,
  clerkUserId: string,
): Promise<Response> => {
  const userId = await getUserRowId(clerkUserId);
  return Response.json({
    settings: await getUserSettings(getDatabase(), userId),
  });
};

/** `PUT /api/settings`: saves all of them, so they follow the user to other devices. */
export const saveSettingsHandler = async (
  request: Request,
  clerkUserId: string,
): Promise<Response> => {
  const limit = writeRateLimiter.take(clerkUserId);
  if (!limit.ok) {
    return createTooManyRequestsResponse(limit.retryAfterMs);
  }

  let body: unknown = null;
  try {
    body = await request.json();
  } catch {
    // Answered as invalid below.
  }
  const parsed = SettingsSchema.safeParse(body);
  if (!parsed.success) {
    return Response.json(
      { error: INVALID_SETTINGS_ERROR },
      { status: INVALID_SETTINGS_STATUS },
    );
  }

  const userId = await getUserRowId(clerkUserId);
  await saveUserSettings(getDatabase(), userId, parsed.data);
  return Response.json({ settings: parsed.data });
};
