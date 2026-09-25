import { defineTool, type ToolDefinition } from "@copilotkit/runtime/v2";
import { ToolParamSchemas, type ToolResult } from "@repo/shared/schemas";

import {
  TOOL_DESCRIPTIONS,
  TOOL_ERRORS,
} from "@/features/agent/constants/tools";
import { runMakeMaterial } from "@/features/agent/services/subagents/material";
import { runResearch } from "@/features/agent/services/subagents/research";
import { runSimplify } from "@/features/agent/services/subagents/simplify";
import { createQuizTools } from "@/features/agent/services/tools/quiz-tools";
import {
  fail,
  runSubagent,
} from "@/features/agent/services/tools/run-subagent";
import { createSurfaceTools } from "@/features/agent/services/tools/surface-tools";
import type { SupervisorRunContext } from "@/features/agent/types/agents";
import { getActiveMaterial } from "@/utils/learning-state";

/** Research, learning material and simplify. */
const createMaterialTools = ({
  settings,
  getState,
  signal,
  env,
  reportDraft,
}: SupervisorRunContext): ToolDefinition[] => [
  defineTool({
    name: "research",
    description: TOOL_DESCRIPTIONS.research,
    parameters: ToolParamSchemas.research,
    execute: ({ topic }): Promise<ToolResult<"research">> =>
      runSubagent("research", { signal }, async () => ({
        topic,
        research: await runResearch({
          topic,
          settings,
          env,
          signal,
          onDraft: (research) => reportDraft({ task: "research", research }),
        }),
      })),
  }),

  defineTool({
    name: "makeMaterial",
    description: TOOL_DESCRIPTIONS.makeMaterial,
    parameters: ToolParamSchemas.makeMaterial,
    execute: async (): Promise<ToolResult<"makeMaterial">> => {
      const { research } = getState();
      if (!research) {
        return fail(TOOL_ERRORS.noResearch);
      }
      return runSubagent("makeMaterial", { signal }, async () => ({
        markdown: await runMakeMaterial({
          research,
          settings,
          signal,
          onDraft: (markdown) => reportDraft({ task: "material", markdown }),
        }),
      }));
    },
  }),

  defineTool({
    name: "simplify",
    description: TOOL_DESCRIPTIONS.simplify,
    parameters: ToolParamSchemas.simplify,
    execute: async ({ scope, selection }): Promise<ToolResult<"simplify">> => {
      const { material } = getState();
      if (!material) {
        return fail(TOOL_ERRORS.noMaterial);
      }
      const text = getActiveMaterial(material);

      if (scope === "all") {
        return runSubagent("simplify", { signal }, async () => ({
          scope,
          markdown: await runSimplify({
            material: text,
            settings,
            signal,
            onDraft: (markdown) => reportDraft({ task: "simplify", markdown }),
          }),
        }));
      }

      if (!selection) {
        return fail(TOOL_ERRORS.noSelection);
      }
      if (!text.includes(selection)) {
        return fail(TOOL_ERRORS.selectionNotFound);
      }
      return runSubagent("simplify", { signal }, async () => ({
        scope,
        selection,
        markdown: await runSimplify({
          material: text,
          selection,
          settings,
          signal,
          // The draft is the whole material with the selection rewritten so far.
          onDraft: (markdown) =>
            reportDraft({
              task: "simplify",
              markdown: text.replace(selection, () => markdown),
            }),
        }),
      }));
    },
  }),
];

/**
 * The server tools for one run. The subagent tools read the settings and the
 * live state from `ctx`, check their prerequisites, and return a result the
 * wrapper writes into state; the surface tools draw in the chat or on the Board.
 */
export const createLearningTools = (
  ctx: SupervisorRunContext,
): ToolDefinition[] => [
  ...createMaterialTools(ctx),
  ...createQuizTools(ctx),
  ...createSurfaceTools(ctx),
];
