"use client";

import { CanvasShellView } from "@/features/canvas/components/CanvasShellView";
import { useCanvasShell } from "@/features/canvas/hooks/use-canvas-shell";

/** The canvas, following the agent's state and the user's stage choice. */
export const CanvasShell = () => {
  const {
    state,
    activeStage,
    step,
    stageNumber,
    stageCount,
    steps,
    progress,
    isBuilding,
    hasData,
    error,
    isQuizOutdated,
    hasPrev,
    hasNext,
    handleSelectStage,
    handlePrev,
    handleNext,
  } = useCanvasShell();

  return (
    <CanvasShellView
      state={state}
      activeStage={activeStage}
      step={step}
      stageNumber={stageNumber}
      stageCount={stageCount}
      steps={steps}
      progress={progress}
      isBuilding={isBuilding}
      hasData={hasData}
      error={error}
      isQuizOutdated={isQuizOutdated}
      hasPrev={hasPrev}
      hasNext={hasNext}
      onSelectStage={handleSelectStage}
      onPrev={handlePrev}
      onNext={handleNext}
    />
  );
};
