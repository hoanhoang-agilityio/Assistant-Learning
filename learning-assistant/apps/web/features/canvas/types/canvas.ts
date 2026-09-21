import type { LearningState, Stage } from "@repo/shared/schemas";
import type { LucideIcon } from "lucide-react";

/** A stage the canvas can show; `idle` has no view of its own. */
export type CanvasStage = Exclude<Stage, "idle">;

export interface StageStep {
  id: CanvasStage;
  title: string;
  description: string;
  icon: LucideIcon;
  /** What to do to fill this stage, shown while it is empty. */
  emptyHint: string;
  /** The state key whose data unlocks this stage. */
  dataKey: keyof LearningState;
}

export type StageDirection = "prev" | "next";

/** One stage in the stepper bar, with its display state worked out. */
export interface StepperStep extends Pick<StageStep, "id" | "title" | "icon"> {
  isActive: boolean;
  isUnlocked: boolean;
  /** Has data and is not the stage on screen. */
  isCompleted: boolean;
  /** Its subagent is running. */
  isBuilding: boolean;
}

/** One choice in an `OptionToggle`. */
export interface ToggleOption<T extends string> {
  id: T;
  label: string;
  icon: LucideIcon;
}
