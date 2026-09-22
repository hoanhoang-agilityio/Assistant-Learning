import { defineTool, type ToolDefinition } from "@copilotkit/runtime/v2";
import {
  type QuizSubmission,
  ToolParamSchemas,
  type ToolResult,
} from "@repo/shared/schemas";

import {
  TOOL_DESCRIPTIONS,
  TOOL_ERRORS,
} from "@/features/agent/constants/tools";
import { createSealedQuiz } from "@/features/agent/services/answer-key/seal-quiz";
import { runEvaluation } from "@/features/agent/services/evaluate";
import { runQuiz } from "@/features/agent/services/subagents/quiz";
import {
  fail,
  runSubagent,
} from "@/features/agent/services/tools/run-subagent";
import type { SupervisorRunContext } from "@/features/agent/types/agents";
import { validateSubmission } from "@/features/agent/utils/submission";
import { getActiveNotes } from "@/utils/learning-state";

/**
 * Grades the quiz. The Submit button runs this straight from the wrapper with
 * the answers it sent (`submission`); the `evaluate` tool runs it with the
 * answers in state.
 */
export const runEvaluateStep = async (
  { settings, getState, signal, answerKeys }: SupervisorRunContext,
  submission?: QuizSubmission,
): Promise<ToolResult<"evaluate">> => {
  const state = getState();
  const check = validateSubmission(state, submission);
  if (!check.ok) {
    return fail(check.error);
  }

  return runSubagent("evaluate", { signal }, () =>
    runEvaluation({
      quiz: check.quiz,
      answers: check.answers,
      answerKeys,
      notes: state.notes ? getActiveNotes(state.notes) : "",
      settings,
      signal,
    }),
  );
};

/** `generateQuiz` and `evaluate`. */
export const createQuizTools = (
  ctx: SupervisorRunContext,
): ToolDefinition[] => [
  defineTool({
    name: "generateQuiz",
    description: TOOL_DESCRIPTIONS.generateQuiz,
    parameters: ToolParamSchemas.generateQuiz,
    execute: async (): Promise<ToolResult<"generateQuiz">> => {
      const { settings, getState, signal, answerKeys } = ctx;
      const { notes } = getState();
      if (!notes) {
        return fail(TOOL_ERRORS.noNotesForQuiz);
      }

      return runSubagent("generateQuiz", { signal }, async () => {
        const draft = await runQuiz({
          notes: getActiveNotes(notes),
          count: settings.questionCount,
          settings,
          signal,
        });
        return { quiz: await createSealedQuiz(draft, answerKeys) };
      });
    },
  }),

  defineTool({
    name: "evaluate",
    description: TOOL_DESCRIPTIONS.evaluate,
    parameters: ToolParamSchemas.evaluate,
    execute: () => runEvaluateStep(ctx),
  }),
];
