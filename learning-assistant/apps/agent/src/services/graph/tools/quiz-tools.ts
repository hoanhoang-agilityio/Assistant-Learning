import { ToolParamSchemas } from "@repo/shared/schemas";
import { getActiveMaterial } from "@repo/shared/utils/learning-state";
import { tool } from "langchain";

import { TOOL_DESCRIPTIONS, TOOL_ERRORS } from "../../../constants/tools";
import type { SubagentToolDeps } from "../../../types/graph";
import { validateSubmission } from "../../../utils/submission";
import { createSealedQuiz } from "../../answer-key/seal-quiz";
import { runEvaluation } from "../../evaluate";
import { runQuiz } from "../../subagents/quiz";
import {
  failStep,
  runSubagentStep,
  type SubagentToolRuntime,
} from "./subagent-step";

/** `generateQuiz` and `evaluate`. */
export const createQuizTools = ({ apiKey, answerKeys }: SubagentToolDeps) => [
  tool(
    (_args, runtime: SubagentToolRuntime) =>
      runSubagentStep("generateQuiz", runtime, apiKey, async (step) => {
        const { material } = step.state;
        if (!material) {
          return failStep(TOOL_ERRORS.noMaterialForQuiz);
        }
        const draft = await runQuiz({
          material: getActiveMaterial(material),
          count: step.settings.questionCount,
          settings: step.settings,
          signal: step.signal,
          // The draft holds the questions only; the answers stay here.
          onDraft: (questions) => step.reportDraft({ task: "quiz", questions }),
        });
        const quiz = await createSealedQuiz(draft, answerKeys);
        return {
          ok: true,
          update: { quiz, quizOutdated: false },
          summary: { questionCount: quiz.questions.length },
        };
      }),
    {
      name: "generateQuiz",
      description: TOOL_DESCRIPTIONS.generateQuiz,
      schema: ToolParamSchemas.generateQuiz,
    },
  ),

  tool(
    (_args, runtime: SubagentToolRuntime) =>
      runSubagentStep("evaluate", runtime, apiKey, async (step) => {
        // A Submit press carries its own answers; a chat request to grade
        // uses the ones in state.
        const check = validateSubmission(
          step.state,
          runtime.context.submit?.submission,
        );
        if (!check.ok) {
          return failStep(check.error);
        }
        const { answers, evaluation, score, feedback } = await runEvaluation({
          quiz: check.quiz,
          answers: check.answers,
          answerKeys,
          material: step.state.material
            ? getActiveMaterial(step.state.material)
            : "",
          settings: step.settings,
          signal: step.signal,
          onDraft: (draft) => step.reportDraft({ task: "evaluate", ...draft }),
        });
        return {
          ok: true,
          update: {
            evaluation,
            score,
            feedback,
            quiz: { ...check.quiz, answers, submitted: true },
          },
          summary: {
            correct: evaluation.correct,
            total: evaluation.total,
            weakestConcept: evaluation.weakestConcept,
            score,
          },
        };
      }),
    {
      name: "evaluate",
      description: TOOL_DESCRIPTIONS.evaluate,
      schema: ToolParamSchemas.evaluate,
    },
  ),
];
