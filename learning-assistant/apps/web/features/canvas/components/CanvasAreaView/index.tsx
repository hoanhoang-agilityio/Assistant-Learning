import type { BoardDraft, BoardSurface } from "@repo/shared/schemas";
import { LayoutDashboard, type LucideIcon, Route } from "lucide-react";
import type { ReactNode } from "react";

import { BoardShell } from "@/features/canvas/components/BoardShell";
import { CanvasShell } from "@/features/canvas/components/CanvasShell";
import { BOARD_COPY, CANVAS_VIEW_IDS } from "@/features/canvas/constants/board";
import type { CanvasView } from "@/features/canvas/types/board";

export interface CanvasAreaViewProps {
  view: CanvasView;
  surfaces: BoardSurface[];
  boardDraft: BoardDraft | null;
  /** A Board view arrived while the stages were showing. */
  hasUnseen: boolean;
  onSelectView: (view: CanvasView) => void;
}

interface TabProps {
  view: CanvasView;
  icon: LucideIcon;
  label: string;
  isSelected: boolean;
  onSelect: () => void;
  children?: ReactNode;
}

const Tab = ({
  view,
  icon: Icon,
  label,
  isSelected,
  onSelect,
  children,
}: TabProps) => (
  <button
    type="button"
    role="tab"
    id={CANVAS_VIEW_IDS[view].tab}
    aria-selected={isSelected}
    aria-controls={CANVAS_VIEW_IDS[view].panel}
    onClick={onSelect}
    className={`flex items-center gap-1.5 rounded-lg px-3 py-1.5 text-xs font-medium transition-colors ${
      isSelected
        ? "bg-indigo-600 text-white shadow-sm"
        : "text-slate-600 hover:bg-slate-100 dark:text-slate-300 dark:hover:bg-slate-800"
    }`}
  >
    <Icon className="h-3.5 w-3.5" />
    {label}
    {children}
  </button>
);

/**
 * Both views stay mounted and the hidden one is only hidden, so switching
 * keeps the stage the student was on and anything typed in it.
 */
export const CanvasAreaView = ({
  view,
  surfaces,
  boardDraft,
  hasUnseen,
  onSelectView,
}: CanvasAreaViewProps) => (
  <div className="flex min-w-0 flex-1 flex-col overflow-hidden">
    <div
      role="tablist"
      className="flex items-center gap-1 border-b border-slate-200 bg-white px-4 py-1.5 dark:border-slate-800 dark:bg-slate-900"
    >
      <Tab
        view="stages"
        icon={Route}
        label={BOARD_COPY.stagesTab}
        isSelected={view === "stages"}
        onSelect={() => onSelectView("stages")}
      />
      <Tab
        view="board"
        icon={LayoutDashboard}
        label={BOARD_COPY.boardTab}
        isSelected={view === "board"}
        onSelect={() => onSelectView("board")}
      >
        {surfaces.length > 0 && (
          <span className="rounded-full bg-black/10 px-1.5 text-[10px] dark:bg-white/15">
            {surfaces.length}
          </span>
        )}
        {hasUnseen && (
          <span className="rounded-full bg-rose-500 px-1.5 text-[10px] font-semibold text-white">
            {BOARD_COPY.newBadge}
          </span>
        )}
      </Tab>
    </div>

    <div
      role="tabpanel"
      id={CANVAS_VIEW_IDS.stages.panel}
      aria-labelledby={CANVAS_VIEW_IDS.stages.tab}
      className={`min-h-0 flex-1 ${view === "stages" ? "flex" : "hidden"}`}
    >
      <CanvasShell />
    </div>
    <div
      role="tabpanel"
      id={CANVAS_VIEW_IDS.board.panel}
      aria-labelledby={CANVAS_VIEW_IDS.board.tab}
      className={`min-h-0 flex-1 ${view === "board" ? "flex" : "hidden"}`}
    >
      <BoardShell surfaces={surfaces} draft={boardDraft} />
    </div>
  </div>
);
