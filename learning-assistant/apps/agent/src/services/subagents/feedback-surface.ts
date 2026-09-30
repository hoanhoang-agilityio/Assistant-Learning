import {
  type A2UIOperation,
  assembleOps,
  RENDER_A2UI_TOOL_DEF,
  runA2UIGenerationWithRecovery,
} from "@ag-ui/a2ui-toolkit";
import {
  type AIMessageChunk,
  HumanMessage,
  SystemMessage,
} from "@langchain/core/messages";
import { parsePartialJson } from "@langchain/core/output_parsers";
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

import { FEEDBACK_SURFACE_ATTEMPTS } from "../../constants/agents";
import { SILENT_RUN_METADATA } from "../../constants/openai";
import type { RunSettings } from "../../types/llm";
import type { EvaluatorInput } from "../../types/scoring";
import { toDraftComponents } from "../../utils/surface-draft";
import { createChatModel } from "../llm/chat-model";
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

/** The one tool the model must call: its schema allows Feedback components only. */
const RENDER_TOOL = {
  name: RENDER_TOOL_NAME,
  description: RENDER_A2UI_TOOL_DEF.function.description,
  schema: FeedbackSurfaceArgsSchema,
};

/** The surface id and catalog are the app's, never the model's. */
const createFeedbackOperations = (components: FeedbackComponent[]) =>
  assembleOps({
    intent: "create",
    surfaceId: FEEDBACK_SURFACE_ID,
    catalogId: FEEDBACK_CATALOG_ID,
    components,
  });

/** The components of a `render_a2ui` call still being written that can be drawn. */
const toDraftOperations = (argsText: string): A2UIOperation[] | null => {
  const args: unknown = parsePartialJson(argsText);
  const components = toDraftComponents(
    (args as { components?: unknown } | null)?.components,
    FeedbackComponentSchema,
  );
  return components ? createFeedbackOperations(components) : null;
};

/**
 * Evaluator Agent, UI part: the model calls `render_a2ui` with components
 * from the Feedback catalog only (the tool's schema allows nothing else). The
 * toolkit validates the tree against the catalog and retries once with the
 * errors. Returns the A2UI operations for `feedback.a2uiOperations`; throws
 * when no attempt is valid, so the caller keeps the plain summary instead.
 * Each attempt streams; with `onDraft`, its components are drawn as they
 * arrive. The calls are marked silent, so inside a tool their tool call stays
 * out of the chat.
 */
export const runFeedbackSurface = async ({
  input,
  settings,
  signal,
  onDraft,
}: FeedbackSurfaceParams): Promise<A2UIOperation[]> => {
  const model = createChatModel(settings.apiKey).bindTools([RENDER_TOOL], {
    tool_choice: RENDER_TOOL_NAME,
  });

  const invokeSubagent = async (system: string) => {
    const stream = await model.stream(
      [
        new SystemMessage(system),
        new HumanMessage(createFeedbackSurfacePrompt(input)),
      ],
      { signal, metadata: SILENT_RUN_METADATA },
    );

    let reply: AIMessageChunk | undefined;
    let argsText = "";
    for await (const chunk of stream) {
      reply = reply ? reply.concat(chunk) : chunk;
      const delta = (chunk.tool_call_chunks ?? [])
        .map(({ args }) => args ?? "")
        .join("");
      if (!delta) {
        continue;
      }
      argsText += delta;
      const operations = onDraft ? toDraftOperations(argsText) : null;
      if (operations) {
        onDraft?.(operations);
      }
    }

    const call = reply?.tool_calls?.find(
      ({ name }) => name === RENDER_TOOL_NAME,
    );
    const parsed = FeedbackSurfaceArgsSchema.safeParse(call?.args);
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
