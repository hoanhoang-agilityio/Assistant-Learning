/** Base path of the CopilotKit runtime route. The client and the route share it. */
export const COPILOT_RUNTIME_URL =
  process.env.NEXT_PUBLIC_RUNTIME_URL || "/api/copilotkit";

/**
 * Request headers the runtime must not pass on to the agent. By default it
 * forwards `authorization` and every custom `x-*` header into the graph's
 * run config, which is recorded in traces; that would include the session
 * token and the sealed OpenAI key. The route reads what it needs itself.
 */
export const FORWARD_HEADERS_POLICY = {
  deny: ["authorization"],
  denyPrefixes: ["x-"],
};

/** `next dev`. The agent event log and the runtime's debug logging run only here. */
export const IS_DEVELOPMENT = process.env.NODE_ENV === "development";
