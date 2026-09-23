import type { LearningLevel, Settings, Theme } from "@repo/shared/schemas";

export interface SettingsActions {
  setQuestionCount: (count: number) => void;
  setLearningLevel: (level: LearningLevel) => void;
  setTheme: (theme: Theme) => void;
}

/** The theme actually on screen: `system` resolved against the device. */
export type ResolvedTheme = Exclude<Theme, "system">;

export interface SettingsStore {
  settings: Settings;
  actions: SettingsActions;
}
