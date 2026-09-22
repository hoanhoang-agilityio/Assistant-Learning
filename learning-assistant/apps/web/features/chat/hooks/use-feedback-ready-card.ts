import { parseEvaluateScore } from "@/features/chat/utils/tool-results";
import { useLearningAgent } from "@/hooks/use-learning-agent";
import { useRequestStage } from "@/hooks/use-stage-request-store";

/**
 * The "Feedback ready" card under a finished `evaluate` call. It shows only
 * while that feedback is still in state (a retake or new quiz clears it), and
 * opens the Feedback stage on the canvas.
 */
export const useFeedbackReadyCard = (result: string | undefined) => {
  const { state } = useLearningAgent();
  const requestStage = useRequestStage();
  const score = parseEvaluateScore(result);

  return {
    score,
    isVisible: score !== null && state.feedback !== null,
    handleOpen: () => requestStage("feedback"),
  };
};
