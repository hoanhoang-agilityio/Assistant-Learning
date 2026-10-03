import {
  getDraftAnswersHandler,
  saveDraftAnswersHandler,
} from "@/features/conversations/services/conversations-api";
import { withSignedInUser } from "@/services/auth";

export const GET = withSignedInUser(getDraftAnswersHandler);
export const PUT = withSignedInUser(saveDraftAnswersHandler);
