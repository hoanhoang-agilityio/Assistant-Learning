import type { Env } from "@repo/shared/types/env";

import type { AnswerKeyStore } from "./answer-key";
import type { LearningRecords } from "./records";

/** What the subagent tools of one request share. None of it reaches state. */
export interface SubagentToolDeps {
  /** The user's OpenAI API key, for the subagents' own model calls. */
  apiKey: string;
  /** Server env, for optional keys such as `TAVILY_API_KEY`. */
  env: Env;
  /** Seals the quiz answer key and unseals it to grade the quiz. */
  answerKeys: AnswerKeyStore;
  /** Keeps each completed stage outside the checkpoints. */
  records: LearningRecords;
}

/** A Board tool call's arguments so far, parsed from partial JSON. */
export interface SurfaceCallArgs {
  toolCallId: string;
  toolCallName: string;
  args: unknown;
}
