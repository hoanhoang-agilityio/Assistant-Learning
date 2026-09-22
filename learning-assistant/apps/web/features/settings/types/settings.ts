import type { LearningLevel, Settings, Theme } from "@repo/shared/schemas";

export interface SettingsActions {
  setQuestionCount: (count: number) => void;
  setLearningLevel: (level: LearningLevel) => void;
  setTheme: (theme: Theme) => void;
  toggleTheme: () => void;
}

export interface SettingsStore {
  settings: Settings;
  actions: SettingsActions;
}
