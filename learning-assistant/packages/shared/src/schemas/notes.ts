import { z } from "zod";

/**
 * Notes Agent output, for both `makeNotes` and `simplify`. For a simplified
 * selection, `markdown` is the rewritten selection only.
 */
export const NotesResultSchema = z.object({
  markdown: z.string().min(1),
});

export type NotesResult = z.infer<typeof NotesResultSchema>;
