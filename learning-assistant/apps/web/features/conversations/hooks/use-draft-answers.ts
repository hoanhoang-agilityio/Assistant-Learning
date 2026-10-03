import { readLearningState } from "@repo/shared/utils/learning-state";
import { useEffect, useRef } from "react";

import { DRAFT_ANSWERS_SAVE_DELAY_MS } from "@/features/conversations/constants/conversations";
import { useActiveConversation } from "@/features/conversations/hooks/use-conversation-store";
import {
  fetchDraftAnswers,
  saveDraftAnswers,
} from "@/features/conversations/services/conversations-client";
import {
  applyDraftAnswers,
  toDraftAnswers,
} from "@/features/conversations/utils/draft-answers";
import { useLearningAgent } from "@/hooks/use-learning-agent";
import { useRetakeConversationId } from "@/hooks/use-retake-request-store";

/**
 * Keeps the quiz answers picked between runs, so a reload or a switch does
 * not lose them. Each time a conversation opens, once its state is back (a
 * quiz is there and nothing runs), the kept answers are put back, unless
 * the student has picked since or opened it with a Retake from the Progress
 * page. After that, each change of the answers to a quiz not graded yet is
 * kept after a short pause. Nothing is kept while a run is going: the run
 * carries the answers.
 */
export const useDraftAnswers = () => {
  const { agent, state, isRunning } = useLearningAgent();
  const retakeId = useRetakeConversationId();
  // The open conversation, not `agent.threadId`: the chat moves the agent
  // to it in an effect, after this hook has run.
  const threadId = useActiveConversation()?.id ?? null;
  const restoredRef = useRef<string | null>(null);
  const restoringRef = useRef<string | null>(null);
  const savedRef = useRef<string | null>(null);
  const hasQuiz = state.quiz !== null;
  const draft = toDraftAnswers(state);
  const draftKey = draft ? JSON.stringify(draft) : null;

  // Another conversation: its answers are restored again before any save.
  useEffect(() => {
    restoredRef.current = null;
    savedRef.current = null;
  }, [threadId]);

  useEffect(() => {
    if (!threadId || restoredRef.current === threadId) {
      return;
    }
    // A Retake from the Progress page starts the quiz afresh: nothing to put back.
    if (retakeId === threadId) {
      restoredRef.current = threadId;
      return;
    }
    if (isRunning || !hasQuiz || restoringRef.current === threadId) {
      return;
    }

    restoringRef.current = threadId;
    const before = JSON.stringify(readLearningState(agent.state).quiz);
    const restore = async () => {
      const kept = await fetchDraftAnswers(threadId);
      const current = readLearningState(agent.state);
      const isUntouched =
        agent.threadId === threadId && JSON.stringify(current.quiz) === before;
      if (kept && isUntouched) {
        const next = applyDraftAnswers(current, kept);
        if (next !== current) {
          agent.setState(next);
        }
      }
      const restored = toDraftAnswers(readLearningState(agent.state));
      savedRef.current = restored ? JSON.stringify(restored) : null;
    };
    restore()
      .catch((error: unknown) => {
        console.error("[answers] Restoring the draft answers failed", error);
      })
      .finally(() => {
        if (restoringRef.current === threadId) {
          restoringRef.current = null;
          restoredRef.current = threadId;
        }
      });
  }, [agent, threadId, isRunning, hasQuiz, retakeId]);

  useEffect(() => {
    if (
      !threadId ||
      !draft ||
      !draftKey ||
      isRunning ||
      restoredRef.current !== threadId ||
      draftKey === savedRef.current
    ) {
      return;
    }

    const timer = window.setTimeout(() => {
      saveDraftAnswers(threadId, draft)
        .then(() => {
          savedRef.current = draftKey;
        })
        .catch((error: unknown) => {
          console.error("[answers] Keeping the draft answers failed", error);
        });
    }, DRAFT_ANSWERS_SAVE_DELAY_MS);
    return () => window.clearTimeout(timer);
  }, [threadId, draft, draftKey, isRunning]);
};
