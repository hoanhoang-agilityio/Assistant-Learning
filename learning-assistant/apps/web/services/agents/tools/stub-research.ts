import { defineTool } from "@copilotkit/runtime/v2";
import type { ToolResult } from "@repo/shared/schemas";
import { z } from "zod";

/**
 * Smoke-test stand-in for the real `research` tool (M3.1/M3.3). It returns a
 * canned result without calling a model, which proves the path tool result →
 * `STATE_DELTA` → client. Replace it in M3.3.
 */
export const stubResearchTool = defineTool({
  name: "research",
  description: "Research a topic for the student.",
  parameters: z.object({
    topic: z.string().min(1).describe("Short noun phrase for the topic"),
  }),
  execute: async ({ topic }): Promise<ToolResult<"research">> => ({
    ok: true,
    data: {
      topic,
      research: {
        title: topic,
        summary: `Stub research for "${topic}".`,
        keyInsight: "This is a stub result from the M1.9 smoke test.",
        keyTerms: [],
        sources: [],
      },
    },
  }),
});
