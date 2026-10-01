import { listAttemptsHandler } from "@/features/conversations/services/conversations-api";
import { withSignedInUser } from "@/services/auth";

export const GET = withSignedInUser(listAttemptsHandler);
