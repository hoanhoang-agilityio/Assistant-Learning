import {
  AbstractAgent,
  type BaseEvent,
  EventType,
  type RunAgentInput,
  type RunErrorEvent,
  type RunStartedEvent,
} from "@ag-ui/client";
import { BuiltInAgent } from "@copilotkit/runtime/v2";
import { filter, type Observable, of } from "rxjs";

import { SUPERVISOR_MAX_STEPS } from "@/features/agent/constants/agents";
import { syncStateFromTools } from "@/features/agent/services/state-sync";
import { toSupervisorState } from "@/features/agent/services/supervisor-state";
import type { LearningSupervisorAgentConfig } from "@/features/agent/types/agents";
import { createLanguageModel } from "@/services/llm/language-model";
import { getReasoningOptions } from "@/services/llm/reasoning";
import { resolveRunSettings } from "@/services/llm/run-settings";
import { readLearningState } from "@/utils/learning-state";

/**
 * The inner agent sees a trimmed state, so a state event from its built-in
 * `AGUISendState*` tools would overwrite the client's full state. Only the
 * wrapper changes state.
 */
const isInnerStateEvent = (event: BaseEvent) =>
  event.type === EventType.STATE_SNAPSHOT ||
  event.type === EventType.STATE_DELTA;

/**
 * Thin wrapper around `BuiltInAgent`. On each run it reads
 * `forwardedProps.settings`, builds an inner agent for the chosen model and
 * reasoning effort, passes it a trimmed state and pipes its events through,
 * adding a `STATE_DELTA` for each subagent tool result.
 */
export class LearningSupervisorAgent extends AbstractAgent {
  private config: LearningSupervisorAgentConfig;
  private inner?: BuiltInAgent;

  constructor(config: LearningSupervisorAgentConfig = {}) {
    super();
    this.config = config;
  }

  run(input: RunAgentInput): Observable<BaseEvent> {
    const resolved = resolveRunSettings(
      input.forwardedProps?.settings,
      this.config.env,
    );
    if (!resolved.ok) {
      const started: RunStartedEvent = {
        type: EventType.RUN_STARTED,
        threadId: input.threadId,
        runId: input.runId,
      };
      const failed: RunErrorEvent = {
        type: EventType.RUN_ERROR,
        message: resolved.error,
      };
      return of(started, failed);
    }

    const { settings } = resolved;
    const state = readLearningState(input.state);

    this.inner = new BuiltInAgent({
      model: createLanguageModel(settings.provider, settings.model),
      providerOptions: getReasoningOptions(
        settings.provider,
        settings.model,
        settings.reasoningEffort,
      ),
      maxSteps: this.config.maxSteps ?? SUPERVISOR_MAX_STEPS,
      prompt: this.config.prompt,
      tools: this.config.tools?.({ settings, state }) ?? [],
    });

    return this.inner.run({ ...input, state: toSupervisorState(state) }).pipe(
      filter((event) => !isInnerStateEvent(event)),
      syncStateFromTools(state),
    );
  }

  // The runtime clones the agent for each request, and the base clone does
  // not copy subclass fields.
  clone(): LearningSupervisorAgent {
    const cloned: LearningSupervisorAgent = super.clone();
    cloned.config = this.config;
    cloned.inner = undefined;
    return cloned;
  }

  abortRun(): void {
    this.inner?.abortRun();
  }
}
