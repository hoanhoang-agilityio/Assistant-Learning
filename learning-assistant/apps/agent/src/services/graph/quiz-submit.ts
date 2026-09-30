import { AIMessage, ToolMessage } from "@langchain/core/messages";
import type { SubagentTool } from "@repo/shared/schemas";
import { createMiddleware } from "langchain";
import { z } from "zod";

import { RunContextSchema } from "../../schemas/graph";
import { isToolSuccess } from "../../utils/message-history";
import { ToolCallModel } from "../llm/tool-call-model";

const EVALUATE_TOOL: SubagentTool = "evaluate";

/**
 * A Submit press on the quiz surface (`context.submit`). The quiz is graded
 * in code first: instead of the Supervisor's model, the first model call of
 * the run is answered by a model that only calls `evaluate`, so the chat
 * shows its progress card and the tool writes the result like any other. A
 * graded quiz ends the run there, its card being the whole reply; the real
 * model runs only to explain a failed grading. The LLM never decides whether
 * to grade.
 */
export const quizSubmitMiddleware = createMiddleware({
  name: "QuizSubmit",
  stateSchema: z.object({
    /** A Submit run that has not yet called `evaluate`. Server only. */
    pendingSubmit: z.boolean().default(false),
  }),
  contextSchema: RunContextSchema,
  beforeAgent: (_state, runtime) => ({
    pendingSubmit: runtime.context.submit !== null,
  }),
  wrapModelCall: (request, handler) => {
    if (request.state.pendingSubmit) {
      return handler({
        ...request,
        model: new ToolCallModel({ name: EVALUATE_TOOL, args: {} }),
      });
    }

    const last = request.messages.at(-1);
    const isGraded =
      request.runtime.context.submit !== null &&
      ToolMessage.isInstance(last) &&
      last.name === EVALUATE_TOOL &&
      isToolSuccess(last);
    return isGraded ? new AIMessage("") : handler(request);
  },
  afterModel: (state) =>
    state.pendingSubmit ? { pendingSubmit: false } : undefined,
});
