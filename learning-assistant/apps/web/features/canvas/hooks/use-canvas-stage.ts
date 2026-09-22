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
  toCanvasStage,
} from "@/features/canvas/utils/stages";
import { useStageRequest } from "@/hooks/use-stage-request-store";

/**
 * The stage the canvas shows. It follows the agent (the running stage, then
 * the last finished one), opens a stage another panel asks for, and the user
 * can move between unlocked stages.
 */
export const useCanvasStage = (state: LearningState) => {
  const followed = getFollowedStage(state);
  const request = useStageRequest();
  const [activeStage, setActiveStage] = useState<CanvasStage>(
    followed ?? FIRST_STAGE,
  );
  const [lastFollowed, setLastFollowed] = useState(followed);
  const [lastRequestId, setLastRequestId] = useState(request?.id);

  // Move with the agent when it starts or finishes a stage. Adjusting state
  // during render (not in an effect) avoids painting the old stage first.
  if (followed !== lastFollowed) {
    setLastFollowed(followed);
    setActiveStage(followed ?? FIRST_STAGE);
  }

  if (request && request.id !== lastRequestId) {
    setLastRequestId(request.id);
    const target = toCanvasStage(request.stage);
    if (target && isStageUnlocked(state, target)) {
      setActiveStage(target);
    }
  }

  const prevStage = getAdjacentStage(state, activeStage, "prev");
  const nextStage = getAdjacentStage(state, activeStage, "next");

  const handleSelectStage = (stage: CanvasStage) => {
    if (isStageUnlocked(state, stage)) {
      setActiveStage(stage);
    }
  };

  const handleStep = (direction: StageDirection) => {
    const target = direction === "prev" ? prevStage : nextStage;
    if (target) {
      setActiveStage(target);
    }
  };

  return {
    activeStage,
    prevStage,
    nextStage,
    handleSelectStage,
    handleStep,
  };
};
