import type { SurfaceTemplate } from "@repo/shared/a2ui/surface-template";
import { MASTERED_PERCENT } from "@repo/shared/constants/scoring";
import type {
  Evaluation,
  Quiz,
  ResearchResult,
  Score,
} from "@repo/shared/schemas";
import { getNextTier, getTier } from "@repo/shared/utils/tier";

import {
  A2UI_VERSION,
  DATA_MODEL_ROOT,
} from "@/features/canvas/constants/a2ui";
import {
  NO_WEAKEST_CONCEPT,
  RESULT_LABELS,
  TIER_DESCRIPTIONS,
  TIER_TONE,
  TOP_TIER_REACHED,
} from "@/features/canvas/constants/results";
import type {
  A2UIMessage,
  EvaluationDataModel,
  QuizDataModel,
  ResearchDataModel,
  ScoreDataModel,
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

/**
 * The Evaluation template's data model: accuracy, questions answered and the
 * weakest concept as tiles, then one mastery bar per concept, coloured by the
 * tier its percent falls in.
 */
export const createEvaluationDataModel = ({
  correct,
  total,
  percent,
  weakestConcept,
  mastery,
}: Evaluation): EvaluationDataModel => ({
  tiles: [
    { label: RESULT_LABELS.accuracy, value: `${percent}%`, tone: "indigo" },
    {
      label: RESULT_LABELS.correctAnswers,
      value: `${correct} / ${total}`,
      tone: "indigo",
    },
    {
      label: RESULT_LABELS.weakestConcept,
      value: weakestConcept ?? NO_WEAKEST_CONCEPT,
      tone: weakestConcept ? "amber" : "emerald",
    },
  ],
  mastery: mastery.map(({ concept, percent: conceptPercent }) => ({
    concept,
    percent: conceptPercent,
    tone: TIER_TONE[getTier(conceptPercent)],
    isWeakest: concept === weakestConcept,
  })),
});

/** "Master at 80%", or the top-tier label once there is no tier above. */
export const formatNextTier = (percent: number): string => {
  const next = getNextTier(percent);
  return next ? `${next.tier} at ${next.minPercent}%` : TOP_TIER_REACHED;
};

/** The Score template's data model: the tier, the score and three chips. */
export const createScoreDataModel = (
  { percent, tier }: Score,
  { correct, total, mastery }: Evaluation,
): ScoreDataModel => {
  const mastered = mastery.filter(
    ({ percent: conceptPercent }) => conceptPercent >= MASTERED_PERCENT,
  ).length;

  return {
    percent,
    tier,
    tierDescription: TIER_DESCRIPTIONS[tier],
    chips: [
      { label: RESULT_LABELS.correct, value: `${correct} / ${total}` },
      {
        label: RESULT_LABELS.conceptsMastered,
        value: `${mastered} / ${mastery.length}`,
      },
      { label: RESULT_LABELS.nextTier, value: formatNextTier(percent) },
    ],
  };
};
