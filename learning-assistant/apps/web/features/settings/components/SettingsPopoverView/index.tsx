import {
  CHAT_MODES,
  type ChatMode,
  LEARNING_LEVELS,
  type LearningLevel,
  QUESTION_COUNT,
  type Settings as UserSettings,
  type Theme,
  THEMES,
  VIEW_MODES,
  type ViewMode,
} from "@repo/shared/schemas";
import {
  GraduationCap,
  KeyRound,
  LayoutPanelLeft,
  ListChecks,
  MonitorSmartphone,
  Palette,
  Settings,
  Sliders,
  X,
} from "lucide-react";
import Link from "next/link";
import { type RefObject, useId } from "react";

import { API_KEY_ROUTE } from "@/constants/routes";

const LABEL_CLASS =
  "mb-1 flex items-center gap-1 font-medium text-slate-600 dark:text-slate-300";

const segmentClass = (isSelected: boolean) =>
  `rounded border px-2 py-1 text-center text-[11px] capitalize transition-all disabled:cursor-not-allowed disabled:opacity-40 ${
    isSelected
      ? "border-indigo-600 bg-indigo-600 text-white"
      : "border-slate-200 hover:bg-slate-100 dark:border-slate-700 dark:hover:bg-slate-700"
  }`;

export interface SettingsPopoverViewProps {
  isOpen: boolean;
  /** Wraps the button and the panel; clicks outside it close the popover. */
  containerRef: RefObject<HTMLDivElement | null>;
  settings: UserSettings;
  chatMode: ChatMode;
  viewMode: ViewMode;
  onToggle: () => void;
  onClose: () => void;
  onQuestionCountChange: (count: number) => void;
  onLearningLevelChange: (level: LearningLevel) => void;
  onThemeChange: (theme: Theme) => void;
  onChatModeChange: (mode: ChatMode) => void;
  onViewModeChange: (mode: ViewMode) => void;
}

/** Header button + popover for the API key, quiz and display settings. */
export const SettingsPopoverView = ({
  isOpen,
  containerRef,
  settings,
  chatMode,
  viewMode,
  onToggle,
  onClose,
  onQuestionCountChange,
  onLearningLevelChange,
  onThemeChange,
  onChatModeChange,
  onViewModeChange,
}: SettingsPopoverViewProps) => {
  const panelId = useId();

  return (
    <div ref={containerRef} className="relative">
      <button
        type="button"
        aria-expanded={isOpen}
        aria-controls={panelId}
        onClick={onToggle}
        className={`flex items-center gap-2 rounded-lg border px-3 py-1.5 text-sm font-medium transition-all ${
          isOpen
            ? "border-indigo-300 bg-indigo-50 text-indigo-600 dark:border-indigo-700 dark:bg-indigo-950/40 dark:text-indigo-400"
            : "border-slate-200 text-slate-700 hover:bg-slate-100 dark:border-slate-700 dark:text-slate-200 dark:hover:bg-slate-700"
        }`}
      >
        <Settings className="h-4 w-4" />
        <span>Settings</span>
      </button>

      {isOpen && (
        <div
          id={panelId}
          role="dialog"
          aria-label="Settings"
          className="absolute right-0 z-50 mt-3 w-80 max-w-[calc(100cqw-2rem)] rounded-xl border border-slate-200 bg-white p-4 text-slate-800 shadow-2xl dark:border-slate-700 dark:bg-slate-800 dark:text-slate-200"
        >
          <div className="mb-4 flex items-center justify-between border-b border-slate-200 pb-3 dark:border-slate-700">
            <h3 className="flex items-center gap-2 text-sm font-semibold">
              <Sliders className="h-4 w-4 text-indigo-500" /> System Preferences
            </h3>
            <button
              type="button"
              aria-label="Close settings"
              onClick={onClose}
              className="text-slate-400 hover:text-slate-600 dark:hover:text-slate-200"
            >
              <X className="h-4 w-4" />
            </button>
          </div>

          <div className="space-y-4 text-xs">
            <div className="flex items-center justify-between">
              <span className="flex items-center gap-1 font-medium text-slate-600 dark:text-slate-300">
                <KeyRound className="h-3.5 w-3.5" /> OpenAI API key
              </span>
              <Link
                href={API_KEY_ROUTE}
                className="rounded border border-slate-200 px-2 py-1 text-[11px] transition-all hover:bg-slate-100 dark:border-slate-700 dark:hover:bg-slate-700"
              >
                Change
              </Link>
            </div>

            <div>
              <label htmlFor={`${panelId}-count`} className={LABEL_CLASS}>
                <ListChecks className="h-3.5 w-3.5" /> Quiz Questions
                <span className="ml-auto font-semibold text-indigo-600 tabular-nums dark:text-indigo-400">
                  {settings.questionCount}
                </span>
              </label>
              <input
                id={`${panelId}-count`}
                type="range"
                min={QUESTION_COUNT.min}
                max={QUESTION_COUNT.max}
                step={1}
                value={settings.questionCount}
                onChange={(e) => onQuestionCountChange(Number(e.target.value))}
                className="w-full cursor-pointer accent-indigo-600"
              />
              <div className="flex justify-between text-[10px] text-slate-400">
                <span>{QUESTION_COUNT.min}</span>
                <span>{QUESTION_COUNT.max}</span>
              </div>
            </div>

            <fieldset>
              <legend className={LABEL_CLASS}>
                <GraduationCap className="h-3.5 w-3.5" /> Learning Level
              </legend>
              <div className="grid grid-cols-3 gap-1">
                {LEARNING_LEVELS.map((level) => (
                  <button
                    key={level}
                    type="button"
                    aria-pressed={settings.learningLevel === level}
                    onClick={() => onLearningLevelChange(level)}
                    className={segmentClass(settings.learningLevel === level)}
                  >
                    {level}
                  </button>
                ))}
              </div>
            </fieldset>

            <fieldset className="border-t border-slate-100 pt-3 dark:border-slate-700">
              <legend className="sr-only">Theme</legend>
              <div className="flex items-center justify-between">
                <span className="flex items-center gap-1.5 text-slate-600 dark:text-slate-300">
                  <Palette className="h-3.5 w-3.5" /> Theme
                </span>
                <div className="grid grid-cols-3 gap-1">
                  {THEMES.map((theme) => (
                    <button
                      key={theme}
                      type="button"
                      aria-pressed={settings.theme === theme}
                      onClick={() => onThemeChange(theme)}
                      className={segmentClass(settings.theme === theme)}
                    >
                      {theme}
                    </button>
                  ))}
                </div>
              </div>
            </fieldset>

            <fieldset>
              <legend className={LABEL_CLASS}>
                <LayoutPanelLeft className="h-3.5 w-3.5" /> Chat
              </legend>
              <div className="grid grid-cols-3 gap-1">
                {CHAT_MODES.map((mode) => (
                  <button
                    key={mode}
                    type="button"
                    aria-pressed={chatMode === mode}
                    onClick={() => onChatModeChange(mode)}
                    className={segmentClass(chatMode === mode)}
                  >
                    {mode}
                  </button>
                ))}
              </div>
            </fieldset>

            <fieldset>
              <legend className={LABEL_CLASS}>
                <MonitorSmartphone className="h-3.5 w-3.5" /> View
              </legend>
              <div className="grid grid-cols-4 gap-1">
                {VIEW_MODES.map((mode) => (
                  <button
                    key={mode}
                    type="button"
                    aria-pressed={viewMode === mode}
                    onClick={() => onViewModeChange(mode)}
                    className={segmentClass(viewMode === mode)}
                  >
                    {mode}
                  </button>
                ))}
              </div>
            </fieldset>
          </div>
        </div>
      )}
    </div>
  );
};
