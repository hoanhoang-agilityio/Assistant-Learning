import {
  type A2UIOperation,
  assembleOps,
  RENDER_A2UI_TOOL_DEF,
  runA2UIGenerationWithRecovery,
} from "@ag-ui/a2ui-toolkit";
import {
  FEEDBACK_CATALOG,
  FEEDBACK_CATALOG_ID,
  FEEDBACK_SURFACE_ID,
} from "@repo/shared/a2ui/feedback-catalog";
import { FeedbackSurfaceArgsSchema, type Settings } from "@repo/shared/schemas";
import { generateText, tool } from "ai";

import { FEEDBACK_SURFACE_ATTEMPTS } from "@/features/agent/constants/agents";
import {
  createFeedbackSurfacePrompt,
  createFeedbackSurfaceSystem,
} from "@/features/agent/services/prompts/evaluator";
import type { EvaluatorInput } from "@/features/agent/types/scoring";
import { createLanguageModel } from "@/services/llm/language-model";
import { getReasoningOptions } from "@/services/llm/reasoning";

interface FeedbackSurfaceParams {
  input: EvaluatorInput;
  settings: Settings;
  signal?: AbortSignal;
}

const RENDER_TOOL_NAME = RENDER_A2UI_TOOL_DEF.function.name;

/**
 * Evaluator Agent, UI part: the model calls `render_a2ui` with components
 * from the Feedback catalog only (the tool's schema allows nothing else). The
 * toolkit validates the tree against the catalog and retries once with the
 * errors. Returns the A2UI operations for `feedback.a2uiOperations`; throws
 * when no attempt is valid, so the caller keeps the plain summary instead.
 */
export const runFeedbackSurface = async ({
  input,
  settings,
  signal,
}: FeedbackSurfaceParams): Promise<A2UIOperation[]> => {
  const invokeSubagent = async (system: string) => {
    const { toolCalls } = await generateText({
      model: createLanguageModel(settings.provider, settings.model),
      providerOptions: getReasoningOptions(
        settings.provider,
        settings.model,
        settings.reasoningEffort,
      ),
      system,
      prompt: createFeedbackSurfacePrompt(input),
      tools: {
        [RENDER_TOOL_NAME]: tool({
          description: RENDER_A2UI_TOOL_DEF.function.description,
          inputSchema: FeedbackSurfaceArgsSchema,
        }),
      },
      toolChoice: { type: "tool", toolName: RENDER_TOOL_NAME },
      abortSignal: signal,
    });
    const call = toolCalls.find(
      ({ toolName, invalid }) => toolName === RENDER_TOOL_NAME && !invalid,
    );
    const parsed = FeedbackSurfaceArgsSchema.safeParse(call?.input);
    return parsed.success ? parsed.data : null;
  };

  // The surface id and catalog are the app's, never the model's.
  const { ok, envelope, attempts } = await runA2UIGenerationWithRecovery({
    basePrompt: createFeedbackSurfaceSystem(settings.learningLevel),
    catalog: FEEDBACK_CATALOG,
    config: { maxAttempts: FEEDBACK_SURFACE_ATTEMPTS },
    invokeSubagent,
    buildEnvelope: (args) =>
      JSON.stringify(
        assembleOps({
          intent: "create",
          surfaceId: FEEDBACK_SURFACE_ID,
          catalogId: FEEDBACK_CATALOG_ID,
          components: FeedbackSurfaceArgsSchema.parse(args).components,
        }),
      ),
  });

  if (!ok) {
    const errors = attempts.flatMap(({ errors }) => errors);
    throw new Error(
      `The feedback surface was invalid after ${attempts.length} attempts: ${errors
        .map(({ message }) => message)
        .join("; ")}`,
    );
  }
  return JSON.parse(envelope) as A2UIOperation[];
};
