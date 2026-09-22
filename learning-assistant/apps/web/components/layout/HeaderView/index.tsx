import { Moon, Sparkles, Sun } from "lucide-react";

import { SettingsPopover } from "@/features/settings/components/SettingsPopover";

export interface HeaderViewProps {
  isDark: boolean;
  onToggleTheme: () => void;
}

/** App title, theme toggle and the settings popover. */
export const HeaderView = ({ isDark, onToggleTheme }: HeaderViewProps) => (
  <header className="z-20 flex h-16 shrink-0 items-center justify-between border-b border-slate-200 bg-white px-6 dark:border-slate-700 dark:bg-slate-800/90">
    <div className="flex items-center gap-3">
      <div className="flex h-9 w-9 items-center justify-center rounded-xl bg-linear-to-tr from-indigo-500 to-purple-600 text-white shadow-md shadow-indigo-500/20">
        <Sparkles className="h-5 w-5" />
      </div>
      <div>
        <h1 className="text-base leading-tight font-bold tracking-tight">
          Learning Assistant
        </h1>
        <p className="text-xs text-slate-400">
          Interactive Canvas & Real-time Assistant
        </p>
      </div>
    </div>

    <div className="flex items-center gap-3">
      <button
        type="button"
        onClick={onToggleTheme}
        aria-label={isDark ? "Switch to light theme" : "Switch to dark theme"}
        className="rounded-lg p-2 text-slate-600 transition-colors hover:bg-slate-100 dark:text-amber-400 dark:hover:bg-slate-700"
      >
        {isDark ? <Sun className="h-5 w-5" /> : <Moon className="h-5 w-5" />}
      </button>
      <SettingsPopover />
    </div>
  </header>
);
