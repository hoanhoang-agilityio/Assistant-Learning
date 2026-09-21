import type {
  LearningLevel,
  Provider,
  ReasoningEffort,
  Settings,
  Theme,
} from "@repo/shared/schemas";

export interface SettingsActions {
  setProvider: (provider: Provider) => void;
  setModel: (model: string) => void;
  setReasoningEffort: (effort: ReasoningEffort) => void;
  setQuestionCount: (count: number) => void;
  setLearningLevel: (level: LearningLevel) => void;
  setTheme: (theme: Theme) => void;
  toggleTheme: () => void;
  /** Moves off a provider that has no key on the server. */
  reconcileProviders: (available: readonly Provider[]) => void;
}

export interface SettingsStore {
  settings: Settings;
  actions: SettingsActions;
}
