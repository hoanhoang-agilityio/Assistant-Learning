import { FileText, Sparkles, TextSelect } from "lucide-react";
import type { SyntheticEvent } from "react";

import { MarkdownPreview } from "@/features/canvas/components/MarkdownPreview";
import { OptionToggle } from "@/features/canvas/components/OptionToggle";
import { CARD_CLASS } from "@/features/canvas/constants/canvas";
import {
  MATERIAL_MODE_OPTIONS,
  MATERIAL_VIEW_OPTIONS,
} from "@/features/canvas/constants/material";
import type {
  MaterialMode,
  MaterialView,
} from "@/features/canvas/types/material";

export interface MaterialStageViewProps {
  text: string;
  characterCount: number;
  mode: MaterialMode;
  view: MaterialView;
  hasSimplified: boolean;
  /** Text is selected in the editor. */
  hasSelection: boolean;
  /** An edit is waiting to be written to the agent's state. */
  isSaving: boolean;
  /** The agent is running; editing and Simplify wait for it. */
  isLocked: boolean;
  onChange: (text: string) => void;
  onSelect: (event: SyntheticEvent<HTMLTextAreaElement>) => void;
  onModeChange: (mode: MaterialMode) => void;
  onViewChange: (view: MaterialView) => void;
  onSimplifyAll: () => void;
  onSimplifySelection: () => void;
}

const SIMPLIFY_BUTTON_CLASS =
  "flex items-center gap-1 rounded-lg border border-indigo-200 bg-indigo-50 px-2.5 py-1 text-xs text-indigo-600 transition-colors hover:bg-indigo-100 disabled:cursor-not-allowed disabled:opacity-40 dark:border-indigo-800 dark:bg-indigo-950 dark:text-indigo-400 dark:hover:bg-indigo-900";

const SIMPLIFIED_ONLY: readonly MaterialView[] = ["simplified"];

/** Markdown editor and preview, the view toggles and the Simplify actions. */
export const MaterialStageView = ({
  text,
  characterCount,
  mode,
  view,
  hasSimplified,
  hasSelection,
  isSaving,
  isLocked,
  onChange,
  onSelect,
  onModeChange,
  onViewChange,
  onSimplifyAll,
  onSimplifySelection,
}: MaterialStageViewProps) => (
  <section className={CARD_CLASS}>
    <div className="mb-4 flex flex-wrap items-center justify-between gap-3">
      <h3 className="flex items-center gap-2 text-sm font-bold">
        <FileText className="h-4 w-4 text-indigo-500" /> Learning Material
      </h3>
      <div className="flex flex-wrap items-center gap-2">
        <OptionToggle
          label="Material version"
          options={MATERIAL_VIEW_OPTIONS}
          value={view}
          disabledIds={hasSimplified ? [] : SIMPLIFIED_ONLY}
          onChange={onViewChange}
        />
        <OptionToggle
          label="Editor mode"
          options={MATERIAL_MODE_OPTIONS}
          value={mode}
          onChange={onModeChange}
        />
      </div>
    </div>

    <div className="mb-3 flex flex-wrap gap-2">
      <button
        type="button"
        disabled={isLocked}
        onClick={onSimplifyAll}
        className={SIMPLIFY_BUTTON_CLASS}
      >
        <Sparkles className="h-3 w-3" /> Simplify all
      </button>
      <button
        type="button"
        disabled={isLocked || mode !== "edit" || !hasSelection}
        onClick={onSimplifySelection}
        title="Switch to Edit and select text first"
        className={SIMPLIFY_BUTTON_CLASS}
      >
        <TextSelect className="h-3 w-3" /> Simplify selection
      </button>
    </div>

    {mode === "edit" ? (
      <textarea
        aria-label="Learning material (markdown)"
        value={text}
        readOnly={isLocked}
        onChange={(event) => onChange(event.target.value)}
        onSelect={onSelect}
        rows={18}
        className="w-full rounded-xl border border-slate-200 bg-slate-50 p-4 font-mono text-xs leading-relaxed text-slate-800 transition-all outline-none read-only:opacity-60 focus:border-indigo-500 dark:border-slate-700 dark:bg-slate-900 dark:text-slate-200"
      />
    ) : (
      <MarkdownPreview markdown={text} />
    )}

    <div className="mt-3 flex items-center justify-between text-[11px] text-slate-400">
      <span aria-live="polite">
        {isLocked
          ? "The assistant is working — editing resumes when it's done."
          : isSaving
            ? "Saving…"
            : "Saved to this session"}
      </span>
      <span>{characterCount} characters</span>
    </div>
  </section>
);
