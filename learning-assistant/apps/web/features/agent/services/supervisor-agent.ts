import {
  AbstractAgent,
  type BaseEvent,
  EventType,
  type Message,
  type RunAgentInput,
  type RunErrorEvent,
  type RunStartedEvent,
} from "@ag-ui/client";
import { BuiltInAgent } from "@copilotkit/runtime/v2";
import { filter, type Observable, of } from "rxjs";

import {
  QUIZ_SEAL_SECRET_ENV_KEY,
  SUPERVISOR_MAX_STEPS,
} from "@/features/agent/constants/agents";
import { SealedAnswerKeyStore } from "@/features/agent/services/answer-key/sealed-answer-key-store";
import { explainRunErrors } from "@/features/agent/services/run-errors";
import { syncStateFromTools } from "@/features/agent/services/state-sync";
import { runSubmittedQuiz } from "@/features/agent/services/submit-quiz";
import { toSupervisorState } from "@/features/agent/services/supervisor-state";
import type {
  LearningSupervisorAgentConfig,
  SupervisorRunContext,
} from "@/features/agent/types/agents";
import { formatProviderError } from "@/features/agent/utils/provider-errors";
import { parseSubmitAction } from "@/features/agent/utils/submit-action";
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
 * adding a `STATE_DELTA` for each subagent tool result. A quiz Submit
 * (`forwardedProps.a2uiAction`) is graded before the Supervisor runs. A failed
 * run leaves a readable message in the chat.
 */
export class LearningSupervisorAgent extends AbstractAgent {
  private config: LearningSupervisorAgentConfig;
  private inner?: BuiltInAgent;
  private abortController?: AbortController;

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
      return of(started, failed).pipe(explainRunErrors((message) => message));
    }

    const { settings } = resolved;
    const env = this.config.env ?? process.env;
    const initial = readLearningState(input.state);
    let current = initial;
    this.abortController = new AbortController();

    const ctx: SupervisorRunContext = {
      settings,
      getState: () => current,
      signal: this.abortController.signal,
      env,
      answerKeys:
        this.config.answerKeys ??
        new SealedAnswerKeyStore(env[QUIZ_SEAL_SECRET_ENV_KEY]),
    };

    const inner = new BuiltInAgent({
      model: createLanguageModel(settings.provider, settings.model),
      providerOptions: getReasoningOptions(
        settings.provider,
        settings.model,
        settings.reasoningEffort,
      ),
      maxSteps: this.config.maxSteps ?? SUPERVISOR_MAX_STEPS,
      prompt: this.config.prompt,
      tools: this.config.tools?.(ctx) ?? [],
    });
    this.inner = inner;

    // The Supervisor sees the trimmed state as of when it starts.
    const runSupervisor = (messages: Message[]) =>
      inner.run({
        ...input,
        messages,
        state: toSupervisorState(current, settings),
      });

    // Submit on the quiz surface is graded in code, not routed by the LLM.
    const submit = parseSubmitAction(input.forwardedProps);
    const events = submit
      ? runSubmittedQuiz({
          input,
          ctx,
          submission: submit.submission,
          runSupervisor,
        })
      : runSupervisor(input.messages);

    return events.pipe(
      filter((event) => !isInnerStateEvent(event)),
      syncStateFromTools(initial, (next) => {
        current = next;
      }),
      explainRunErrors((message) => formatProviderError(message, settings)),
    );
  }

  // The runtime clones the agent for each request, and the base clone does
  // not copy subclass fields.
  clone(): LearningSupervisorAgent {
    const cloned: LearningSupervisorAgent = super.clone();
    cloned.config = this.config;
    cloned.inner = undefined;
    cloned.abortController = undefined;
    return cloned;
  }

  abortRun(): void {
    this.abortController?.abort();
    this.inner?.abortRun();
  }
}
