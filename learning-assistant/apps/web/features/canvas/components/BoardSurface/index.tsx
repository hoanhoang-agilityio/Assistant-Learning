import { A2UIProvider } from "@copilotkit/a2ui-renderer";
import type { BoardSurface as BoardSurfaceData } from "@repo/shared/schemas";

import { BoardSurfaceBody } from "@/features/canvas/components/BoardSurfaceBody";
import { BOARD_UI_CATALOG } from "@/features/canvas/constants/board-catalog";

export interface BoardSurfaceProps {
  surface: BoardSurfaceData;
}

/**
 * One Board view with its own provider, so a view that fails to draw never
 * takes the others with it. Changes are announced in the chat, not here.
 */
export const BoardSurface = ({ surface }: BoardSurfaceProps) => (
  <section aria-label={surface.title} className="text-sm">
    <h3 className="mb-3 text-sm font-bold">{surface.title}</h3>
    <A2UIProvider catalog={BOARD_UI_CATALOG}>
      <BoardSurfaceBody surface={surface} />
    </A2UIProvider>
  </section>
);
