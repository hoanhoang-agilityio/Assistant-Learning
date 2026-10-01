import { verifyWebhook } from "@clerk/nextjs/webhooks";
import type { NextRequest } from "next/server";

import {
  INVALID_WEBHOOK_ERROR,
  INVALID_WEBHOOK_STATUS,
  USER_DELETED_EVENT,
} from "@/constants/webhooks";
import { deleteUserData } from "@/services/user-deletion";

/**
 * Clerk's webhook. Nothing in it is trusted until its Svix signature checks
 * out against `CLERK_WEBHOOK_SIGNING_SECRET`; then a deleted user's data is
 * removed. Other events are acknowledged and ignored.
 */
export const handleClerkWebhook = async (
  request: NextRequest,
): Promise<Response> => {
  let event: Awaited<ReturnType<typeof verifyWebhook>>;
  try {
    event = await verifyWebhook(request);
  } catch {
    return Response.json(
      { error: INVALID_WEBHOOK_ERROR },
      { status: INVALID_WEBHOOK_STATUS },
    );
  }

  if (event.type === USER_DELETED_EVENT && event.data.id) {
    await deleteUserData(event.data.id);
  }
  return Response.json({ received: true });
};
