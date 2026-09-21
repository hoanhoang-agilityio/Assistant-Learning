import { defineTool, type ToolDefinition } from "@copilotkit/runtime/v2";
import {
  type SubagentTool,
  ToolParamSchemas,
  type ToolResult,
  type ToolResultData,
} from "@repo/shared/schemas";

import {
  TOOL_DESCRIPTIONS,
  TOOL_ERRORS,
  TOOL_FAILURE_PREFIX,
} from "@/features/agent/constants/tools";
import { runMakeNotes } from "@/features/agent/services/subagents/notes";
import { runResearch } from "@/features/agent/services/subagents/research";
import { runSimplify } from "@/features/agent/services/subagents/simplify";
import type { SupervisorRunContext } from "@/features/agent/types/agents";
import { getActiveNotes } from "@/utils/learning-state";

interface ToolFailure {
  ok: false;
  error: string;
}

const fail = (error: string): ToolFailure => ({ ok: false, error });

/**
 * Runs a subagent and turns any throw into `{ ok: false, error }`. Tools never
 * throw: the wrapper reads the failure into `status.error` and the Supervisor
 * sees it in the tool result, so it can explain instead of retrying blindly.
 */
const runSubagent = async <T extends SubagentTool>(
  tool: T,
  signal: AbortSignal,
  work: () => Promise<ToolResultData<T>>,
): Promise<{ ok: true; data: ToolResultData<T> } | ToolFailure> => {
  try {
    return { ok: true, data: await work() };
  } catch (error) {
    if (signal.aborted) return fail(TOOL_ERRORS.stopped);
    const message = error instanceof Error ? error.message : String(error);
    console.error(`[${tool}]`, error);
    return fail(`${TOOL_FAILURE_PREFIX[tool]}: ${message}`);
  }
};

/**
 * The Research and Notes subagent tools for one run. They read the settings
 * and the live state from `ctx`, check their prerequisites, and return a
 * result the wrapper writes into state.
 */
export const createLearningTools = ({
  settings,
  getState,
  signal,
  env,
}: SupervisorRunContext): ToolDefinition[] => [
  defineTool({
    name: "research",
    description: TOOL_DESCRIPTIONS.research,
    parameters: ToolParamSchemas.research,
    execute: ({ topic }): Promise<ToolResult<"research">> =>
      runSubagent("research", signal, async () => ({
        topic,
        research: await runResearch({ topic, settings, env, signal }),
      })),
  }),

  defineTool({
    name: "makeNotes",
    description: TOOL_DESCRIPTIONS.makeNotes,
    parameters: ToolParamSchemas.makeNotes,
    execute: async (): Promise<ToolResult<"makeNotes">> => {
      const { research } = getState();
      if (!research) return fail(TOOL_ERRORS.noResearch);
      return runSubagent("makeNotes", signal, async () => ({
        markdown: await runMakeNotes({ research, settings, signal }),
      }));
    },
  }),

  defineTool({
    name: "simplify",
    description: TOOL_DESCRIPTIONS.simplify,
    parameters: ToolParamSchemas.simplify,
    execute: async ({ scope, selection }): Promise<ToolResult<"simplify">> => {
      const { notes } = getState();
      if (!notes) return fail(TOOL_ERRORS.noNotes);
      const text = getActiveNotes(notes);

      if (scope === "all") {
        return runSubagent("simplify", signal, async () => ({
          scope,
          markdown: await runSimplify({ notes: text, settings, signal }),
        }));
      }

      if (!selection) return fail(TOOL_ERRORS.noSelection);
      if (!text.includes(selection)) return fail(TOOL_ERRORS.selectionNotFound);
      return runSubagent("simplify", signal, async () => ({
        scope,
        selection,
        markdown: await runSimplify({
          notes: text,
          selection,
          settings,
          signal,
        }),
      }));
    },
  }),
];
