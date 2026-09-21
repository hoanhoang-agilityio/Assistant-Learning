import type { Notes } from "@repo/shared/schemas";

/** Whether the Notes stage shows the editor or the rendered markdown. */
export type NotesMode = "edit" | "preview";

export type NotesView = Notes["view"];
