import type { LearningState, Settings } from "@repo/shared/schemas";

import type { SupervisorState } from "@/features/agent/types/agents";
import { getActiveMaterial } from "@/utils/learning-state";

/**
 * Trims the state to what the Supervisor needs to choose the next step, plus
 * the settings it must respect (so it never guesses a question count or level).
 */
export const toSupervisorState = (
  {
    stage,
    status,
    topic,
    research,
    material,
    quiz,
    evaluation,
    score,
    feedback,
    reflection,
    quizOutdated,
    board,
  }: LearningState,
  { questionCount, learningLevel }: Settings,
): SupervisorState => ({
  settings: { questionCount, learningLevel },
  stage,
  status,
  topic,
  research: research && {
    title: research.title,
    keyInsight: research.keyInsight,
  },
  material: material && {
    view: material.view,
    hasSimplified: material.simplified !== null,
    characters: getActiveMaterial(material).length,
  },
  quiz: quiz && {
    questionCount: quiz.questions.length,
    answeredCount: Object.keys(quiz.answers).length,
    submitted: quiz.submitted,
  },
  evaluation: evaluation && {
    correct: evaluation.correct,
    total: evaluation.total,
    weakestConcept: evaluation.weakestConcept,
  },
  score,
  hasFeedback: feedback !== null,
  hasReflection: reflection !== null,
  quizOutdated,
  board: board.map(({ id, title }) => ({ id, title })),
});
