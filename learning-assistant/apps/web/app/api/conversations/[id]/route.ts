import {
  deleteConversationHandler,
  getConversationHandler,
  renameConversationHandler,
} from "@/features/conversations/services/conversations-api";
import { withSignedInUser } from "@/services/auth";

export const GET = withSignedInUser(getConversationHandler);
export const PATCH = withSignedInUser(renameConversationHandler);
export const DELETE = withSignedInUser(deleteConversationHandler);
