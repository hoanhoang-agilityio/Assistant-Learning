import {
  createConversationHandler,
  listConversationsHandler,
} from "@/features/conversations/services/conversations-api";
import { withSignedInUser } from "@/services/auth";

export const GET = withSignedInUser(listConversationsHandler);
export const POST = withSignedInUser(createConversationHandler);
