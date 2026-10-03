import { retakeQuiz } from "@repo/shared/utils/client-edits";
import { readLearningState } from "@repo/shared/utils/learning-state";
import { useEffect, useRef } from "react";

import { useLearningAgent } from "@/hooks/use-learning-agent";
import {
  useRetakeConversationId,
  useRetakeRequestActions,
} from "@/hooks/use-retake-request-store";
import { useRequestStage } from "@/hooks/use-stage-request-store";

/**
 * Carries out a Retake asked for from the History page, on the conversation
 * the bootstrap opened for it: the graded results are cleared like the
 * quiz's own Retake (`agent.setState`, sent with the next run) and the Quiz
 * stage opens. The state comes back from the checkpoint in a replay that
 * counts as a run, and a later replay (the chat reconnecting) would bring
 * the graded quiz back; so the request holds for that quiz, and is applied
 * again after each, until the student picks an answer or a different quiz
 * arrives. Opening another conversation drops it too (the sidebar does),
 * and a conversation with no quiz drops it once a replay has ended.
 */
export const useRetakeFromHistory = () => {
  const conversationId = useRetakeConversationId();
  const { clearRetake } = useRetakeRequestActions();
  const requestStage = useRequestStage();
  const { agent, state, isRunning } = useLearningAgent();
  const hasReplayedRef = useRef(false);
  const quizIdRef = useRef<string | null>(null);
  const { quiz } = state;

  useEffect(() => {
    if (!conversationId) {
      hasReplayedRef.current = false;
      quizIdRef.current = null;
      return;
    }
    // Until the chat has moved the agent to the conversation, its state is
    // not that conversation's yet.
    if (agent.threadId !== conversationId) {
      return;
    }
    if (isRunning) {
      hasReplayedRef.current = true;
      return;
    }
    if (!quiz) {
      if (hasReplayedRef.current) {
        clearRetake();
      }
      return;
    }

    const isFirst = quizIdRef.current === null;
    quizIdRef.current ??= quiz.id;
    const hasStarted = !quiz.submitted && Object.keys(quiz.answers).length > 0;
    if (quiz.id !== quizIdRef.current || hasStarted) {
      clearRetake();
      return;
    }

    if (quiz.submitted) {
      agent.setState(retakeQuiz(readLearningState(agent.state)));
    }
    if (quiz.submitted || isFirst) {
      requestStage("quiz");
    }
  }, [conversationId, agent, isRunning, quiz, requestStage, clearRetake]);
};
