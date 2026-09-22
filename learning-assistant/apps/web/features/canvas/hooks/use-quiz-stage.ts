import type { A2UIClientEventMessage } from "@copilotkit/a2ui-renderer";
import { QUIZ_ACTIONS } from "@repo/shared/a2ui/quiz-actions";
import type { Evaluation, LearningState, Quiz } from "@repo/shared/schemas";
import { useMemo } from "react";

import { NEW_QUESTIONS_MESSAGE } from "@/features/canvas/constants/quiz";
import { useSendMessage } from "@/features/canvas/hooks/use-send-message";
import { useSubmitQuiz } from "@/features/canvas/hooks/use-submit-quiz";
import { createQuizDataModel } from "@/features/canvas/utils/build-surface";
import {
  parseSelectAnswer,
  retakeQuiz,
  selectAnswer,
} from "@/features/canvas/utils/quiz-answers";
import { useLearningAgent } from "@/hooks/use-learning-agent";
import { readLearningState } from "@/utils/learning-state";

/**
 * The Quiz surface's data model and its actions. A choice and Retake change
 * the agent's state from the client (`agent.setState`); Submit starts a run
 * that carries the action in `forwardedProps`, and the agent grades it in
 * code; New questions asks the assistant in chat. Nothing is accepted while
 * the agent runs.
 */
export const useQuizStage = (quiz: Quiz, evaluation: Evaluation | null) => {
  const { agent, isRunning } = useLearningAgent();
  const sendMessage = useSendMessage();
  const submit = useSubmitQuiz();

  const dataModel = useMemo(
    () => createQuizDataModel(quiz, evaluation, isRunning),
    [quiz, evaluation, isRunning],
  );

  const updateState = (update: (state: LearningState) => LearningState) => {
    const current = readLearningState(agent.state);
    const next = update(current);
    if (next !== current) {
      agent.setState(next);
    }
  };

  const handleAction = (message: A2UIClientEventMessage) => {
    const action = message.userAction;
    if (!action || agent.isRunning) {
      return;
    }

    switch (action.name) {
      case QUIZ_ACTIONS.selectAnswer: {
        const choice = parseSelectAnswer(action.context);
        if (choice) {
          updateState((state) => selectAnswer(state, choice));
        }
        return;
      }
      case QUIZ_ACTIONS.submit:
        submit(message);
        return;
      case QUIZ_ACTIONS.retake:
        updateState(retakeQuiz);
        return;
      case QUIZ_ACTIONS.newQuestions:
        sendMessage(NEW_QUESTIONS_MESSAGE);
        return;
    }
  };

  return { dataModel, handleAction };
};
