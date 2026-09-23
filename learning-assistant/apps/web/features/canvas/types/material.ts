import type { Material } from "@repo/shared/schemas";

/** Whether the Learning Material stage shows the editor or the rendered markdown. */
export type MaterialMode = "preview" | "edit";

export type MaterialView = Material["view"];
