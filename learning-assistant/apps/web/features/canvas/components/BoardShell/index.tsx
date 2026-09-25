import type {
  BoardDraft,
  BoardSurface as BoardSurfaceData,
} from "@repo/shared/schemas";
import { LayoutDashboard } from "lucide-react";

import { BoardDraftSurface } from "@/features/canvas/components/BoardDraftSurface";
import { BoardSurface } from "@/features/canvas/components/BoardSurface";
import { BOARD_COPY } from "@/features/canvas/constants/board";
import { CARD_CLASS } from "@/features/canvas/constants/canvas";

export interface BoardShellProps {
  /** Oldest first, as in state; drawn newest first. */
  surfaces: BoardSurfaceData[];
  /** The view being written, drawn first; a revision hides the view it revises. */
  draft: BoardDraft | null;
}

/**
 * The canvas Board: the dynamic A2UI views the Supervisor made, apart from
 * the learning stages, or a hint on how to add one while it is empty. It is a container, so Columns can lay out by the
 * Board's width rather than the window's.
 */
export const BoardShell = ({ surfaces, draft }: BoardShellProps) => (
  <main className="flex min-w-0 flex-1 flex-col overflow-hidden bg-slate-50/50 dark:bg-slate-900/50">
    <div className="flex items-center gap-2 border-b border-slate-200 bg-white/80 px-6 py-2 dark:border-slate-800 dark:bg-slate-800/40">
      <span className="shrink-0 rounded-md bg-indigo-100 px-2.5 py-1 text-xs font-semibold text-indigo-600 dark:bg-indigo-950/80 dark:text-indigo-300">
        {BOARD_COPY.title}
      </span>
      <span className="truncate text-xs text-slate-400">
        {BOARD_COPY.description}
      </span>
    </div>

    <div className="@container flex-1 overflow-y-auto p-6">
      <div className="mx-auto max-w-4xl space-y-8">
        {surfaces.length === 0 && !draft && (
          <div
            className={`${CARD_CLASS} flex min-h-64 flex-col items-center justify-center gap-3 text-center`}
          >
            <span className="flex h-12 w-12 items-center justify-center rounded-2xl bg-indigo-50 text-indigo-500 dark:bg-indigo-950/60 dark:text-indigo-300">
              <LayoutDashboard className="h-6 w-6" />
            </span>
            <h3 className="text-sm font-bold">{BOARD_COPY.emptyTitle}</h3>
            <p className="max-w-sm text-xs leading-relaxed text-slate-500 dark:text-slate-400">
              {BOARD_COPY.emptyHint}
            </p>
          </div>
        )}
        {draft && <BoardDraftSurface key={`draft:${draft.id}`} draft={draft} />}
        {[...surfaces]
          .reverse()
          .filter(({ id }) => id !== draft?.id)
          .map((surface) => (
            // Keyed by revision too, so a revised view is drawn from scratch.
            <BoardSurface
              key={`${surface.id}#${surface.revision}`}
              surface={surface}
            />
          ))}
      </div>
    </div>
  </main>
);
