import { STAGE_STEPS } from "@/features/canvas/constants/stages";
import { useCanvasStage } from "@/features/canvas/hooks/use-canvas-stage";
import { useStageRetry } from "@/features/canvas/hooks/use-stage-retry";
import {
  calculateStageProgress,
  getRunningStage,
  getStageIndex,
  getStageStep,
  getStepperSteps,
  hasStageData,
} from "@/features/canvas/utils/stages";
import { useLearningAgent } from "@/hooks/use-learning-agent";

/**
 * Everything the canvas draws: the stepper, the stage header, a failed task
 * with Retry, and the stage.
 */
export const useCanvasShell = () => {
  const { state, isRunning } = useLearningAgent();
  const { activeStage, prevStage, nextStage, handleSelectStage, handleStep } =
    useCanvasStage(state);
  const { canRetry, isRetryDisabled, handleRetry } = useStageRetry(
    state,
    isRunning,
  );

  return {
    state,
    activeStage,
    step: getStageStep(activeStage),
    stageNumber: getStageIndex(activeStage) + 1,
    stageCount: STAGE_STEPS.length,
    steps: getStepperSteps(state, activeStage),
    progress: calculateStageProgress(state),
    isBuilding: getRunningStage(state) === activeStage,
    hasData: hasStageData(state, activeStage),
    error: state.status.error ?? null,
    canRetry,
    isRetryDisabled,
    isQuizOutdated: state.quizOutdated && activeStage !== "research",
    hasPrev: prevStage !== null,
    hasNext: nextStage !== null,
    handleSelectStage,
    handleRetry,
    handlePrev: () => handleStep("prev"),
    handleNext: () => handleStep("next"),
  };
};
