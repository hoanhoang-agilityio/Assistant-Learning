import type { LearningState, Stage } from "@repo/shared/schemas";

import {
  DRAFT_STAGES,
  RUNNING_TASK_STAGE,
  STAGE_STEPS,
} from "@/features/canvas/constants/stages";
import type {
  CanvasStage,
  StageDirection,
  StageStep,
  StepperStep,
} from "@/features/canvas/types/canvas";

/** The canvas stage for `stage`; `idle` has none. */
export const toCanvasStage = (stage: Stage): CanvasStage | null =>
  stage === "idle" ? null : stage;

export const getStageStep = (stage: CanvasStage): StageStep => {
  const step = STAGE_STEPS.find(({ id }) => id === stage);
  if (!step) {
    throw new Error(`Unknown stage: ${stage}`);
  }
  return step;
};

export const getStageIndex = (stage: CanvasStage): number => {
  return STAGE_STEPS.findIndex(({ id }) => id === stage);
};

/** The stage whose subagent is running, or `null`. */
export const getRunningStage = (state: LearningState): CanvasStage | null => {
  const { running } = state.status;
  return running ? RUNNING_TASK_STAGE[running] : null;
};

export const hasStageData = (
  state: LearningState,
  stage: CanvasStage,
): boolean => {
  return state[getStageStep(stage).dataKey] != null;
};

/** The stage's subagent is running, or the running task's draft fills it. */
export const isStageBuilding = (
  state: LearningState,
  stage: CanvasStage,
): boolean =>
  getRunningStage(state) === stage ||
  (state.draft !== null && DRAFT_STAGES[state.draft.task].includes(stage));

/** A stage can be opened once its data exists, or while it is being built. */
export const isStageUnlocked = (
  state: LearningState,
  stage: CanvasStage,
): boolean => {
  return hasStageData(state, stage) || isStageBuilding(state, stage);
};

/**
 * The stage the canvas should move to on its own: the running stage first,
 * then the stage the agent last finished. `null` before any work.
 */
export const getFollowedStage = (state: LearningState): CanvasStage | null => {
  return (
    getRunningStage(state) ?? (state.stage === "idle" ? null : state.stage)
  );
};

/** The nearest unlocked stage before or after `from`, or `null`. */
export const getAdjacentStage = (
  state: LearningState,
  from: CanvasStage,
  direction: StageDirection,
): CanvasStage | null => {
  const index = getStageIndex(from);
  const candidates =
    direction === "next"
      ? STAGE_STEPS.slice(index + 1)
      : STAGE_STEPS.slice(0, index).reverse();
  return candidates.find(({ id }) => isStageUnlocked(state, id))?.id ?? null;
};

/** How far the stepper bar is filled, in percent: up to the last unlocked stage. */
export const calculateStageProgress = (state: LearningState): number => {
  const lastUnlocked = STAGE_STEPS.reduce(
    (last, { id }, index) => (isStageUnlocked(state, id) ? index : last),
    0,
  );
  return (lastUnlocked / (STAGE_STEPS.length - 1)) * 100;
};

/** Every stage with the flags the stepper draws it from. */
export const getStepperSteps = (
  state: LearningState,
  activeStage: CanvasStage,
): StepperStep[] => {
  return STAGE_STEPS.map(({ id, title, icon }) => {
    const isActive = id === activeStage;
    return {
      id,
      title,
      icon,
      isActive,
      isUnlocked: isStageUnlocked(state, id),
      isCompleted: hasStageData(state, id) && !isActive,
      isBuilding: isStageBuilding(state, id),
    };
  });
};
