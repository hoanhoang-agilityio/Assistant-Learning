import { A2UIProvider } from "@copilotkit/a2ui-renderer";
import type { BoardDraft } from "@repo/shared/schemas";

import { StreamingNote } from "@/features/canvas/components/StreamingNote";
import { SurfaceDraftBody } from "@/features/canvas/components/SurfaceDraftBody";
import { BOARD_COPY } from "@/features/canvas/constants/board";
import { BOARD_UI_CATALOG } from "@/features/canvas/constants/board-catalog";

export interface BoardDraftSurfaceProps {
  draft: BoardDraft;
}

/** The Board view the assistant is writing, drawn as its components arrive. */
export const BoardDraftSurface = ({ draft }: BoardDraftSurfaceProps) => (
  <section aria-label={draft.title} aria-busy="true" className="text-sm">
    <div className="mb-3 flex items-center justify-between gap-3">
      <h3 className="text-sm font-bold">{draft.title}</h3>
      <StreamingNote label={BOARD_COPY.writing} />
    </div>
    <A2UIProvider catalog={BOARD_UI_CATALOG}>
      <SurfaceDraftBody surfaceId={draft.id} operations={draft.operations} />
    </A2UIProvider>
  </section>
);
