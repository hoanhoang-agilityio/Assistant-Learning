import {
  CopilotRuntime,
  createCopilotRuntimeHandler,
} from "@copilotkit/runtime/v2";
import { BuiltInAgent } from "@copilotkit/runtime/v2";

const builtInAgent = new BuiltInAgent({
  model: "openai:gpt-5.4-mini",
});

const runtime = new CopilotRuntime({
  agents: { default: builtInAgent },
});

const handler = createCopilotRuntimeHandler({
  runtime,
  basePath: "/api/copilotkit",
});

export const GET = handler;
export const POST = handler;
export const PATCH = handler;
export const DELETE = handler;
