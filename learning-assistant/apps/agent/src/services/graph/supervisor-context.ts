import { readLearningState } from "@repo/shared/utils/learning-state";
import { createMiddleware } from "langchain";

import {
  LearningGraphStateSchema,
  RunContextSchema,
} from "../../schemas/graph";
import { findUnsummarized } from "../../utils/conversation-summary";
import { answerOpenToolCalls } from "../../utils/message-history";
import { formatSupervisorContext } from "../../utils/supervisor-context";
import { toSupervisorState } from "../supervisor-state";

/**
 * Builds what the Supervisor reads on each model call, without writing any
 * of it to state: its prompt, then what is kept about the student, the
 * summary of the conversation's older messages, the app context the run
 * was started with (`useAgentContext` entries reach the graph only in the
 * run context) and the state, trimmed to what it needs to choose the next
 * step; and only the messages the summary does not cover, with every tool
 * call answered (see `answerOpenToolCalls`). `messages` itself keeps the
 * whole thread. Declaring the state schema is what puts those keys in
 * `request.state`; without it the request holds only `messages`.
 *
 * It also asks for one tool call at a time: two tools writing the same state
 * key in one step would fail the run.
 */
export const supervisorContextMiddleware = createMiddleware({
  name: "SupervisorContext",
  stateSchema: LearningGraphStateSchema,
  contextSchema: RunContextSchema,
  wrapModelCall: (request, handler) => {
    const { settings, appContext, memory } = request.runtime.context;
    const { summary, summarizedUpTo } = request.state;
    const state = toSupervisorState(readLearningState(request.state), settings);
    const recent = findUnsummarized(request.messages, summarizedUpTo);

    return handler({
      ...request,
      messages: answerOpenToolCalls(recent),
      systemMessage: request.systemMessage.concat(
        `\n\n${formatSupervisorContext({ state, appContext, summary, memory })}`,
      ),
      modelSettings: { ...request.modelSettings, parallel_tool_calls: false },
    });
  },
});
