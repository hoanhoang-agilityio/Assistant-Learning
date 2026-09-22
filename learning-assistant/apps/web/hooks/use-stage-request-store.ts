import { create } from "zustand";

import type { StageRequestStore } from "@/types/stage-request";

/**
 * Lets the chat and the canvas surfaces ask the canvas to open a stage. The
 * canvas opens it if it is unlocked. Not persisted: a request is a moment.
 */
export const useStageRequestStore = create<StageRequestStore>()((set) => ({
  request: null,
  actions: {
    requestStage: (stage) =>
      set(({ request }) => ({
        request: { stage, id: (request?.id ?? 0) + 1 },
      })),
  },
}));

export const useStageRequest = () =>
  useStageRequestStore((store) => store.request);

export const useRequestStage = () =>
  useStageRequestStore((store) => store.actions.requestStage);
