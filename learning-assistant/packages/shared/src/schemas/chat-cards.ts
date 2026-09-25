import { z } from "zod";

/**
 * Arguments of the chat card tools (`CHAT_CARD_TOOLS`). Each schema is also
 * the props of its card, so the model's arguments are drawn as they are.
 */

/** `showConceptCard`: what one term means. */
export const ConceptCardParamsSchema = z.object({
  term: z.string().min(1).describe('The concept\'s name, e.g. "Closure"'),
  definition: z
    .string()
    .min(1)
    .describe("One or two plain sentences at the student's level"),
  example: z
    .string()
    .min(1)
    .optional()
    .describe("One short concrete example, only if it helps"),
});

/** `showComparison`: two things side by side, aspect by aspect. */
export const ComparisonParamsSchema = z.object({
  left: z.string().min(1).describe('First thing compared, e.g. "let"'),
  right: z.string().min(1).describe('Second thing compared, e.g. "const"'),
  rows: z
    .array(
      z.object({
        aspect: z.string().min(1).describe('What is compared, e.g. "Scope"'),
        left: z.string().min(1).describe("How the first thing does it"),
        right: z.string().min(1).describe("How the second thing does it"),
      }),
    )
    .min(2)
    .max(6)
    .describe("Two to six aspects where they differ"),
  verdict: z
    .string()
    .min(1)
    .optional()
    .describe("One sentence on when to pick which"),
});

/** `showSteps`: an ordered process. */
export const StepsParamsSchema = z.object({
  title: z
    .string()
    .min(1)
    .describe('What the steps do, e.g. "How JWT login works"'),
  steps: z
    .array(
      z.object({
        title: z.string().min(1).describe("The step in a few words"),
        detail: z.string().min(1).describe("One sentence on what happens"),
      }),
    )
    .min(2)
    .max(8)
    .describe("Two to eight steps, in order"),
});

/** `showCodeExample`: a short snippet and what it shows. */
export const CodeExampleParamsSchema = z.object({
  title: z.string().min(1).describe("What the code shows"),
  language: z.string().min(1).describe('e.g. "javascript", "python", "sql"'),
  code: z.string().min(1).describe("At most about 20 lines, runnable as is"),
  explanation: z
    .string()
    .min(1)
    .describe("One or two sentences on the line or idea that matters"),
});

export type ConceptCardParams = z.infer<typeof ConceptCardParamsSchema>;
export type ComparisonParams = z.infer<typeof ComparisonParamsSchema>;
export type StepsParams = z.infer<typeof StepsParamsSchema>;
export type CodeExampleParams = z.infer<typeof CodeExampleParamsSchema>;
