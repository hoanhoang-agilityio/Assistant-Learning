import { STAGE_STEPS } from "@/features/canvas/constants/stages";
import { useCanvasStage } from "@/features/canvas/hooks/use-canvas-stage";
import {
  calculateStageProgress,
  getRunningStage,
  getStageIndex,
  getStageStep,
  getStepperSteps,
  hasStageData,
} from "@/features/canvas/utils/stages";
import { useLearningAgent } from "@/hooks/use-learning-agent";

/** Everything the canvas draws: the stepper, the stage header and the stage. */
export const useCanvasShell = () => {
  const { state } = useLearningAgent();
  const { activeStage, prevStage, nextStage, handleSelectStage, handleStep } =
    useCanvasStage(state);

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
    isQuizOutdated: state.quizOutdated && activeStage !== "research",
    hasPrev: prevStage !== null,
    hasNext: nextStage !== null,
    handleSelectStage,
    handlePrev: () => handleStep("prev"),
    handleNext: () => handleStep("next"),
  };
};
