import type { LearningState } from "@repo/shared/schemas";
import { useState } from "react";

import { FIRST_STAGE } from "@/features/canvas/constants/stages";
import type {
  CanvasStage,
  StageDirection,
} from "@/features/canvas/types/canvas";
import {
  getAdjacentStage,
  getFollowedStage,
  isStageUnlocked,
} from "@/features/canvas/utils/stages";

/**
 * The stage the canvas shows. It follows the agent (the running stage, then
 * the last finished one) and the user can move between unlocked stages.
 */
export const useCanvasStage = (state: LearningState) => {
  const followed = getFollowedStage(state);
  const [activeStage, setActiveStage] = useState<CanvasStage>(
    followed ?? FIRST_STAGE,
  );
  const [lastFollowed, setLastFollowed] = useState(followed);

  // Move with the agent when it starts or finishes a stage. Adjusting state
  // during render (not in an effect) avoids painting the old stage first.
  if (followed !== lastFollowed) {
    setLastFollowed(followed);
    setActiveStage(followed ?? FIRST_STAGE);
  }

  const prevStage = getAdjacentStage(state, activeStage, "prev");
  const nextStage = getAdjacentStage(state, activeStage, "next");

  const handleSelectStage = (stage: CanvasStage) => {
    if (isStageUnlocked(state, stage)) setActiveStage(stage);
  };

  const handleStep = (direction: StageDirection) => {
    const target = direction === "prev" ? prevStage : nextStage;
    if (target) setActiveStage(target);
  };

  return {
    activeStage,
    prevStage,
    nextStage,
    handleSelectStage,
    handleStep,
  };
};
