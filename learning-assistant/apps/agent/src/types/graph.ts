import type { Env } from "@repo/shared/types/env";

import type { AnswerKeyStore } from "./answer-key";

/** What the subagent tools of one request share. None of it reaches state. */
export interface SubagentToolDeps {
  /** The user's OpenAI API key, for the subagents' own model calls. */
  apiKey: string;
  /** Server env, for optional keys such as `TAVILY_API_KEY`. */
  env: Env;
  /** Seals the quiz answer key and unseals it to grade the quiz. */
  answerKeys: AnswerKeyStore;
}
