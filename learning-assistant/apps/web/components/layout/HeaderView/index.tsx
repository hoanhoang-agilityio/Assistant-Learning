import { UserButton } from "@clerk/nextjs";
import { HISTORY_ROUTE } from "@repo/shared/constants/routes";
import { Moon, Sparkles, Sun, TrendingUp } from "lucide-react";
import Link from "next/link";

import { SettingsPopover } from "@/features/settings/components/SettingsPopover";

export interface HeaderViewProps {
  isDark: boolean;
  onToggleTheme: () => void;
}

/**
 * App title, theme toggle, the Progress page link, the settings popover and
 * Clerk's user menu. Breakpoints are container
 * queries, so a previewed device frame gets the narrow header too. While the
 * settings popover is open the header rises above the chat popup (z 1200),
 * which otherwise covers it; only then, so a full-screen popup on a phone
 * keeps its own header on top.
 */
export const HeaderView = ({ isDark, onToggleTheme }: HeaderViewProps) => (
  <header className="z-20 flex h-16 shrink-0 items-center justify-between gap-2 border-b border-slate-200 bg-white px-3 has-[[role=dialog]]:z-[1300] @md:px-4 @2xl:px-6 dark:border-slate-700 dark:bg-slate-800/90">
    <div className="flex min-w-0 items-center gap-2 @md:gap-3">
      <div className="flex h-9 w-9 shrink-0 items-center justify-center rounded-xl bg-linear-to-tr from-indigo-500 to-purple-600 text-white shadow-md shadow-indigo-500/20">
        <Sparkles className="h-5 w-5" />
      </div>
      <div className="min-w-0">
        <h1 className="truncate text-base leading-tight font-bold tracking-tight">
          Learning Assistant
        </h1>
        <p className="hidden text-xs text-slate-400 @2xl:block">
          Interactive Canvas & Real-time Assistant
        </p>
      </div>
    </div>

    <div className="flex shrink-0 items-center gap-1.5 @md:gap-3">
      <button
        type="button"
        onClick={onToggleTheme}
        aria-label={isDark ? "Switch to light theme" : "Switch to dark theme"}
        className="rounded-lg p-2 text-slate-600 transition-colors hover:bg-slate-100 dark:text-amber-400 dark:hover:bg-slate-700"
      >
        {isDark ? <Sun className="h-5 w-5" /> : <Moon className="h-5 w-5" />}
      </button>
      <Link
        href={HISTORY_ROUTE}
        aria-label="Progress"
        className="flex items-center gap-2 rounded-lg border border-slate-200 px-2.5 py-1.5 text-sm font-medium text-slate-700 transition-all hover:bg-slate-100 @md:px-3 dark:border-slate-700 dark:text-slate-200 dark:hover:bg-slate-700"
      >
        <TrendingUp className="h-4 w-4" />
        <span className="hidden @2xl:inline">Progress</span>
      </Link>
      <SettingsPopover />
      <UserButton />
    </div>
  </header>
);
