import { createOpenAI } from "@ai-sdk/openai";
import type { LanguageModel } from "ai";

import { OPENAI_MODEL } from "@/constants/openai";

/** The OpenAI model, called with the user's own key; nothing is read from env. */
export const createLanguageModel = (apiKey: string): LanguageModel =>
  createOpenAI({ apiKey })(OPENAI_MODEL);
