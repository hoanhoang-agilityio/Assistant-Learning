/** Base path of the CopilotKit runtime route. The client and the route share it. */
export const COPILOT_RUNTIME_URL =
  process.env.NEXT_PUBLIC_RUNTIME_URL || "/api/copilotkit";

/** `next dev`. The agent event log and the runtime's debug logging run only here. */
export const IS_DEVELOPMENT = process.env.NODE_ENV === "development";
