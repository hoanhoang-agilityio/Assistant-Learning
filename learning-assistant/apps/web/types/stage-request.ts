import type { Stage } from "@repo/shared/schemas";

/**
 * A request, from outside the canvas, to show a stage (a chat card or a link
 * on a surface). `id` changes on every request, so asking for the same stage
 * twice still moves the canvas.
 */
export interface StageRequest {
  stage: Stage;
  id: number;
}

export interface StageRequestStore {
  request: StageRequest | null;
  actions: {
    requestStage: (stage: Stage) => void;
  };
}
