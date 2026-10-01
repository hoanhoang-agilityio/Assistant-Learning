import { handleClerkWebhook } from "@/services/clerk-webhook";

/** Signed by Clerk, not by a session: `withSignedInUser` does not apply. */
export const POST = handleClerkWebhook;
