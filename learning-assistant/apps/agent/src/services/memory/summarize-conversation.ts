import type { BaseMessage } from "@langchain/core/messages";

import { ConversationSummarySchema } from "../../schemas/memory";
import type { RunSettings } from "../../types/llm";
import { formatTranscript } from "../../utils/conversation-summary";
import { createSummaryPrompt, SUMMARY_SYSTEM } from "../prompts/memory";
import { generateStructured } from "../subagents/generate-structured";

interface SummarizeParams {
  settings: RunSettings;
  /** The summary so far; `null` before the first one. */
  previous: string | null;
  /** The messages to fold into it, oldest first. */
  messages: BaseMessage[];
  signal?: AbortSignal;
}

/**
 * One summary of the earlier summary and the messages after it (E1b). The
 * call is silent like a subagent's: its tokens never reach the chat.
 */
export const summarizeConversation = async ({
  settings,
  previous,
  messages,
  signal,
}: SummarizeParams): Promise<string> => {
  const { summary } = await generateStructured({
    settings,
    system: SUMMARY_SYSTEM,
    prompt: createSummaryPrompt(previous, formatTranscript(messages)),
    schema: ConversationSummarySchema,
    signal,
  });
  return summary.trim();
};
