import { readLearningState } from "@repo/shared/utils/learning-state";
import { createMiddleware } from "langchain";

import {
  LearningGraphStateSchema,
  RunContextSchema,
} from "../../schemas/graph";
import { formatSupervisorContext } from "../../utils/supervisor-context";
import { toSupervisorState } from "../supervisor-state";

/**
 * Builds what the Supervisor reads on each model call, without writing any
 * of it to state: its prompt, then the app context the run was started with
 * (`useAgentContext` entries do not reach the model through
 * `copilotkitMiddleware`) and the state, trimmed to what it needs to choose
 * the next step. Declaring the state schema is what puts those keys in
 * `request.state`; without it the request holds only `messages`.
 */
export const supervisorContextMiddleware = createMiddleware({
  name: "SupervisorContext",
  stateSchema: LearningGraphStateSchema,
  contextSchema: RunContextSchema,
  wrapModelCall: (request, handler) => {
    const { settings, appContext } = request.runtime.context;
    const state = toSupervisorState(readLearningState(request.state), settings);

    return handler({
      ...request,
      systemMessage: request.systemMessage.concat(
        `\n\n${formatSupervisorContext(state, appContext)}`,
      ),
    });
  },
});
