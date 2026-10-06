import { createAutoTitle } from "@repo/shared/utils/conversations";

import {
  TITLE_INPUT_MAX_CHARS,
  TITLE_TIMEOUT_MS,
} from "../../constants/memory";
import { ConversationTitleSchema } from "../../schemas/memory";
import { createTitlePrompt, TITLE_SYSTEM } from "../prompts/memory";
import { generateStructured } from "../subagents/generate-structured";

interface SummarizeTitleParams {
  /** The user's OpenAI API key. */
  apiKey: string;
  /** The first message the student wrote in the conversation. */
  userText: string;
}

/**
 * A short title for a new conversation, summarised from the student's
 * first message and cut to the length of an automatic title. Throws when
 * the call fails, takes longer than `TITLE_TIMEOUT_MS`, or names nothing.
 */
export const summarizeTitle = async ({
  apiKey,
  userText,
}: SummarizeTitleParams): Promise<string> => {
  const { title } = await generateStructured({
    settings: { apiKey },
    system: TITLE_SYSTEM,
    prompt: createTitlePrompt(userText.slice(0, TITLE_INPUT_MAX_CHARS)),
    schema: ConversationTitleSchema,
    signal: AbortSignal.timeout(TITLE_TIMEOUT_MS),
  });
  const cut = createAutoTitle(
    title.trim().replace(/^["'“”]+|["'“”.!?]+$/g, ""),
  );
  if (!cut) {
    throw new Error("The title came back empty");
  }
  return cut;
};
