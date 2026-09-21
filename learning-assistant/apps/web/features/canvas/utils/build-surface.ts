import type { SurfaceTemplate } from "@repo/shared/a2ui/surface-template";
import type { Evaluation, Quiz, ResearchResult } from "@repo/shared/schemas";

import {
  A2UI_VERSION,
  DATA_MODEL_ROOT,
} from "@/features/canvas/constants/a2ui";
import type {
  A2UIMessage,
  QuizDataModel,
  ResearchDataModel,
} from "@/features/canvas/types/a2ui";

/** `createSurface` + `updateComponents`: the fixed part of a surface. */
export const createSurfaceMessages = ({
  surfaceId,
  catalogId,
  components,
}: SurfaceTemplate): A2UIMessage[] => [
  { version: A2UI_VERSION, createSurface: { surfaceId, catalogId } },
  { version: A2UI_VERSION, updateComponents: { surfaceId, components } },
];

/** `updateDataModel` replacing the whole data model with the stage's data. */
export const createDataModelMessage = (
  surfaceId: string,
  dataModel: object,
): A2UIMessage => ({
  version: A2UI_VERSION,
  updateDataModel: { surfaceId, path: DATA_MODEL_ROOT, value: dataModel },
});

/** Every message that renders `template` with `dataModel`, in order. */
export const buildSurface = (
  template: SurfaceTemplate,
  dataModel: object,
): A2UIMessage[] => [
  ...createSurfaceMessages(template),
  createDataModelMessage(template.surfaceId, dataModel),
];

/** The Research template's data model; its bindings read `/research/…`. */
export const createResearchDataModel = (
  research: ResearchResult,
): ResearchDataModel => ({ research });

/**
 * The Quiz template's data model: one item per question with the student's
 * choice, plus the Submit state. Results appear only once the quiz is graded;
 * before that there are none to show.
 */
export const createQuizDataModel = (
  quiz: Quiz,
  evaluation: Evaluation | null,
  isLocked: boolean,
): QuizDataModel => {
  const results = new Map(
    quiz.submitted && evaluation
      ? evaluation.perQuestion.map(({ qid, ...result }) => [qid, result])
      : [],
  );
  const questions = quiz.questions.map(
    ({ id, concept, question, options }, index) => ({
      id,
      number: index + 1,
      concept,
      question,
      options,
      selectedIndex: quiz.answers[id] ?? null,
      result: results.get(id) ?? null,
    }),
  );
  const answeredCount = questions.filter(
    ({ selectedIndex }) => selectedIndex !== null,
  ).length;

  return {
    quizId: quiz.id,
    questions,
    answers: quiz.answers,
    answeredCount,
    total: questions.length,
    canSubmit:
      !quiz.submitted &&
      questions.length > 0 &&
      answeredCount === questions.length,
    isSubmitted: quiz.submitted,
    isLocked,
  };
};
