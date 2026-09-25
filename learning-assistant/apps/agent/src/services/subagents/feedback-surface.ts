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
import {
  type FeedbackComponent,
  FeedbackComponentSchema,
  FeedbackSurfaceArgsSchema,
} from "@repo/shared/schemas";
import { generateText, parsePartialJson, streamText, tool } from "ai";

import { FEEDBACK_SURFACE_ATTEMPTS } from "../../constants/agents";
import { OPENAI_CALL_OPTIONS } from "../../constants/openai";
import type { RunSettings } from "../../types/llm";
import type { EvaluatorInput } from "../../types/scoring";
import { toDraftComponents } from "../../utils/surface-draft";
import { createLanguageModel } from "../llm/language-model";
import {
  createFeedbackSurfacePrompt,
  createFeedbackSurfaceSystem,
} from "../prompts/evaluator";

interface FeedbackSurfaceParams {
  input: EvaluatorInput;
  settings: RunSettings;
  signal?: AbortSignal;
  /** Streams the surface: called with its operations so far. */
  onDraft?: (operations: A2UIOperation[]) => void;
}

const RENDER_TOOL_NAME = RENDER_A2UI_TOOL_DEF.function.name;

const RENDER_TOOLS = {
  [RENDER_TOOL_NAME]: tool({
    description: RENDER_A2UI_TOOL_DEF.function.description,
    inputSchema: FeedbackSurfaceArgsSchema,
  }),
};

/** The surface id and catalog are the app's, never the model's. */
const createFeedbackOperations = (components: FeedbackComponent[]) =>
  assembleOps({
    intent: "create",
    surfaceId: FEEDBACK_SURFACE_ID,
    catalogId: FEEDBACK_CATALOG_ID,
    components,
  });

type RenderCallOptions = Parameters<
  typeof generateText<typeof RENDER_TOOLS>
>[0];

/**
 * Streams the render call: each time its arguments grow, the components
 * complete so far are drawn. Returns the call's tool calls; a failed stream
 * throws the provider's own error.
 */
const streamRenderCall = async (
  options: RenderCallOptions,
  onDraft: (operations: A2UIOperation[]) => void,
) => {
  let streamError: unknown;
  const result = streamText({
    ...options,
    onError: ({ error }) => {
      streamError = error;
    },
  });
  let text = "";
  try {
    for await (const part of result.fullStream) {
      if (part.type !== "tool-input-delta") {
        continue;
      }
      text += part.delta;
      const { value } = await parsePartialJson(text);
      const components = toDraftComponents(
        (value as { components?: unknown } | undefined)?.components,
        FeedbackComponentSchema,
      );
      if (components) {
        onDraft(createFeedbackOperations(components));
      }
    }
    return await result.toolCalls;
  } catch (error) {
    throw streamError ?? error;
  }
};

/**
 * Evaluator Agent, UI part: the model calls `render_a2ui` with components
 * from the Feedback catalog only (the tool's schema allows nothing else). The
 * toolkit validates the tree against the catalog and retries once with the
 * errors. Returns the A2UI operations for `feedback.a2uiOperations`; throws
 * when no attempt is valid, so the caller keeps the plain summary instead.
 * With `onDraft`, each attempt streams and its components are drawn as they
 * arrive.
 */
export const runFeedbackSurface = async ({
  input,
  settings,
  signal,
  onDraft,
}: FeedbackSurfaceParams): Promise<A2UIOperation[]> => {
  const invokeSubagent = async (system: string) => {
    const options: RenderCallOptions = {
      model: createLanguageModel(settings.apiKey),
      providerOptions: OPENAI_CALL_OPTIONS,
      system,
      prompt: createFeedbackSurfacePrompt(input),
      tools: RENDER_TOOLS,
      toolChoice: { type: "tool", toolName: RENDER_TOOL_NAME },
      abortSignal: signal,
    };
    const toolCalls = onDraft
      ? await streamRenderCall(options, onDraft)
      : (await generateText(options)).toolCalls;
    const call = toolCalls.find(
      ({ toolName, invalid }) => toolName === RENDER_TOOL_NAME && !invalid,
    );
    const parsed = FeedbackSurfaceArgsSchema.safeParse(call?.input);
    return parsed.success ? parsed.data : null;
  };

  const { ok, envelope, attempts } = await runA2UIGenerationWithRecovery({
    basePrompt: createFeedbackSurfaceSystem(settings.learningLevel),
    catalog: FEEDBACK_CATALOG,
    config: { maxAttempts: FEEDBACK_SURFACE_ATTEMPTS },
    invokeSubagent,
    buildEnvelope: (args) =>
      JSON.stringify(
        createFeedbackOperations(
          FeedbackSurfaceArgsSchema.parse(args).components,
        ),
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
