import type { Env } from "@repo/shared/types/env";

import { QUIZ_SEAL_SECRET_ENV_KEY } from "../../../constants/agents";
import type { AnswerKeyStore } from "../../../types/answer-key";
import { SealedAnswerKeyStore } from "../../answer-key/sealed-answer-key-store";
import { createMaterialTools } from "./material-tools";
import { createQuizTools } from "./quiz-tools";

interface SubagentToolOptions {
  /** The user's OpenAI API key, for the subagents' own model calls. */
  apiKey: string;
  /** Server env, for `TAVILY_API_KEY` and `QUIZ_SEAL_SECRET`. Defaults to `process.env`. */
  env?: Env;
  /** Where the quiz answer key is kept. Defaults to sealing it into state. */
  answerKeys?: AnswerKeyStore;
}

/**
 * The Supervisor's subagent tools for one request: research, learning
 * material, simplify, quiz and evaluate. Each checks its prerequisites in
 * the state, runs its subagent, and writes the result to state itself.
 */
export const createSubagentTools = ({
  apiKey,
  env = process.env,
  answerKeys = new SealedAnswerKeyStore(env[QUIZ_SEAL_SECRET_ENV_KEY]),
}: SubagentToolOptions) => {
  const deps = { apiKey, env, answerKeys };
  return [...createMaterialTools(deps), ...createQuizTools(deps)];
};
