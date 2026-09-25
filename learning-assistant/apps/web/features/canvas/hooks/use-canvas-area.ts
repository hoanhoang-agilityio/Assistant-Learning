import type { BoardSurface } from "@repo/shared/schemas";
import { useState } from "react";

import type { CanvasView } from "@/features/canvas/types/board";
import { useLearningAgent } from "@/hooks/use-learning-agent";
import { useStageRequest } from "@/hooks/use-stage-request-store";

/** One key per view version: a new view and a revised one both get a new key. */
const toKeys = (surfaces: BoardSurface[]) =>
  surfaces.map(({ id, revision }) => `${id}#${revision}`);

const SEPARATOR = "|";

/**
 * Which canvas tab is shown: the learning stages (the default) or the
 * Board. It follows the agent like the stepper does. A view starting to
 * stream in, added or revised opens the Board; a view removed does not,
 * since removals are announced in the chat. A learning task starting, or a request to open a
 * stage, opens the stages. The student can switch at any time.
 */
export const useCanvasArea = () => {
  const { state } = useLearningAgent();
  const request = useStageRequest();
  const surfaces = state.board;
  const keys = toKeys(surfaces);
  // Joined so the keys can be kept in state and compared during render.
  const signature = keys.join(SEPARATOR);
  const running = state.status.running;
  const draftId = state.boardDraft?.id ?? null;

  const [view, setView] = useState<CanvasView>("stages");
  const [lastSignature, setLastSignature] = useState(signature);
  // Views on the Board when the canvas mounts count as seen.
  const [seenSignature, setSeenSignature] = useState(signature);
  const [lastRunning, setLastRunning] = useState(running);
  const [lastDraftId, setLastDraftId] = useState(draftId);
  const [lastRequestId, setLastRequestId] = useState(request?.id);

  // Adjusting state during render (not in an effect) avoids painting the
  // old view first, as in `useCanvasStage`.
  if (signature !== lastSignature) {
    const previous = new Set(lastSignature.split(SEPARATOR));
    setLastSignature(signature);
    if (keys.some((key) => !previous.has(key))) {
      setView("board");
      setSeenSignature(signature);
    }
  }
  if (draftId !== lastDraftId) {
    setLastDraftId(draftId);
    if (draftId !== null) {
      setView("board");
    }
  }
  if (running !== lastRunning) {
    setLastRunning(running);
    if (running !== null) {
      setView("stages");
    }
  }
  if (request && request.id !== lastRequestId) {
    setLastRequestId(request.id);
    setView("stages");
  }

  const seen = new Set(seenSignature.split(SEPARATOR));

  const handleSelectView = (next: CanvasView) => {
    setView(next);
    if (next === "board") {
      setSeenSignature(signature);
    }
  };

  return {
    view,
    surfaces,
    boardDraft: state.boardDraft,
    hasUnseen: view === "stages" && keys.some((key) => !seen.has(key)),
    handleSelectView,
  };
};
