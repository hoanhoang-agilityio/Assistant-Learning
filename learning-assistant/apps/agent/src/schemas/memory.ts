import { z } from "zod";

/** The summariser's output: the conversation's older messages, folded. */
export const ConversationSummarySchema = z.object({
  summary: z.string().min(1),
});
