/** The model every agent uses. */
export const OPENAI_MODEL = "gpt-5.4-mini";

/** Low reasoning effort for every model call, as `ChatOpenAI` takes it. */
export const OPENAI_REASONING = { effort: "low" } as const;

/**
 * Run metadata for a model call made inside a tool: the AG-UI adapter then
 * keeps its tokens and tool calls out of the chat. The keys are the
 * adapter's own, not the `copilotkit:`-prefixed ones.
 */
export const SILENT_RUN_METADATA = {
  "emit-messages": false,
  "emit-tool-calls": false,
} as const;

/** Names the JSON schema in a structured-output request. */
export const STRUCTURED_OUTPUT_NAME = "output";
