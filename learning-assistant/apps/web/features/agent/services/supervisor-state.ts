import type { LearningState, Settings } from "@repo/shared/schemas";

import type { SupervisorState } from "@/features/agent/types/agents";
import { getActiveNotes } from "@/utils/learning-state";

/**
 * Trims the state to what the Supervisor needs to choose the next step, plus
 * the settings it must respect (so it never guesses a question count).
 */
export const toSupervisorState = (
  {
    stage,
    status,
    topic,
    research,
    notes,
    quiz,
    score,
    feedback,
    reflection,
    quizOutdated,
  }: LearningState,
  { questionCount }: Settings,
): SupervisorState => ({
  settings: { questionCount },
  stage,
  status,
  topic,
  research: research && {
    title: research.title,
    keyInsight: research.keyInsight,
  },
  notes: notes && {
    view: notes.view,
    hasSimplified: notes.simplified !== null,
    characters: getActiveNotes(notes).length,
  },
  quiz: quiz && {
    questionCount: quiz.questions.length,
    answeredCount: Object.keys(quiz.answers).length,
    submitted: quiz.submitted,
  },
  score,
  hasFeedback: feedback !== null,
  hasReflection: reflection !== null,
  quizOutdated,
});
