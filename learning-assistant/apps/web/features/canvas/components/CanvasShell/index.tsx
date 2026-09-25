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
    draft,
    hasData,
    error,
    canRetry,
    isRetryDisabled,
    isQuizOutdated,
    hasPrev,
    hasNext,
    handleSelectStage,
    handleRetry,
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
      draft={draft}
      hasData={hasData}
      error={error}
      canRetry={canRetry}
      isRetryDisabled={isRetryDisabled}
      isQuizOutdated={isQuizOutdated}
      hasPrev={hasPrev}
      hasNext={hasNext}
      onSelectStage={handleSelectStage}
      onRetry={handleRetry}
      onPrev={handlePrev}
      onNext={handleNext}
    />
  );
};
