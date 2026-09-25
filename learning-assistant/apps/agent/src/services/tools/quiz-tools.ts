import { defineTool, type ToolDefinition } from "@copilotkit/runtime/v2";
import {
  type QuizSubmission,
  ToolParamSchemas,
  type ToolResult,
} from "@repo/shared/schemas";
import { getActiveMaterial } from "@repo/shared/utils/learning-state";

import { TOOL_DESCRIPTIONS, TOOL_ERRORS } from "../../constants/tools";
import type { SupervisorRunContext } from "../../types/agents";
import { validateSubmission } from "../../utils/submission";
import { createSealedQuiz } from "../answer-key/seal-quiz";
import { runEvaluation } from "../evaluate";
import { runQuiz } from "../subagents/quiz";
import { fail, runSubagent } from "./run-subagent";

/**
 * Grades the quiz. The Submit button runs this straight from the wrapper with
 * the answers it sent (`submission`); the `evaluate` tool runs it with the
 * answers in state.
 */
export const runEvaluateStep = async (
  { settings, getState, signal, answerKeys, reportDraft }: SupervisorRunContext,
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
      material: state.material ? getActiveMaterial(state.material) : "",
      settings,
      signal,
      onDraft: (draft) => reportDraft({ task: "evaluate", ...draft }),
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
      const { settings, getState, signal, answerKeys, reportDraft } = ctx;
      const { material } = getState();
      if (!material) {
        return fail(TOOL_ERRORS.noMaterialForQuiz);
      }

      return runSubagent("generateQuiz", { signal }, async () => {
        const draft = await runQuiz({
          material: getActiveMaterial(material),
          count: settings.questionCount,
          settings,
          signal,
          onDraft: (questions) => reportDraft({ task: "quiz", questions }),
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
