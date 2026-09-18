import { z } from "zod";

export const KeyTermSchema = z.object({
  term: z.string().min(1),
  definition: z.string().min(1),
});

export const SourceSchema = z.object({
  title: z.string().min(1),
  url: z.string().min(1).describe("Absolute URL of the source"),
});

/** Research Agent output; stored as-is in `state.research`. */
export const ResearchResultSchema = z.object({
  title: z.string().min(1),
  summary: z.string().min(1).describe("A few paragraphs, plain text"),
  keyInsight: z
    .string()
    .min(1)
    .describe("The single most important idea, one or two sentences"),
  keyTerms: z.array(KeyTermSchema),
  sources: z
    .array(SourceSchema)
    .describe("Cited sources; empty when web search is unavailable"),
});

export type KeyTerm = z.infer<typeof KeyTermSchema>;
export type Source = z.infer<typeof SourceSchema>;
export type ResearchResult = z.infer<typeof ResearchResultSchema>;
