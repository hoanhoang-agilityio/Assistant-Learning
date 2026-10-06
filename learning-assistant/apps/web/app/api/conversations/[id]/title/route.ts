import { summarizeTitleHandler } from "@/features/conversations/services/conversations-api";
import { withSignedInUser } from "@/services/auth";

export const POST = withSignedInUser(summarizeTitleHandler);
