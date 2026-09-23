import { z } from "zod";

/**
 * Material Agent output, for both `makeMaterial` and `simplify`. For a simplified
 * selection, `markdown` is the rewritten selection only.
 */
export const MaterialResultSchema = z.object({
  markdown: z.string().min(1),
});

export type MaterialResult = z.infer<typeof MaterialResultSchema>;
