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
import type { Draft } from "@repo/shared/schemas";
import { readLearningState } from "@repo/shared/utils/learning-state";
import {
  filter,
  finalize,
  map,
  mergeWith,
  type Observable,
  of,
  Subject,
} from "rxjs";

import {
  QUIZ_SEAL_SECRET_ENV_KEY,
  QUIZ_SUBMIT_TURN,
  SUPERVISOR_MAX_STEPS,
} from "../constants/agents";
import { OPENAI_CALL_OPTIONS } from "../constants/openai";
import type {
  LearningSupervisorAgentConfig,
  SupervisorRunContext,
} from "../types/agents";
import { dropA2UIContext } from "../utils/agent-context";
import { formatOpenAIError } from "../utils/openai-errors";
import { parseSubmitAction } from "../utils/submit-action";
import { SealedAnswerKeyStore } from "./answer-key/sealed-answer-key-store";
import { muteRepliesAfterCards } from "./card-replies";
import { streamBoardDrafts, throttleDrafts, toStageDraftEvent } from "./drafts";
import { createLanguageModel } from "./llm/language-model";
import { resolveRunSettings } from "./llm/run-settings";
import { explainRunErrors } from "./run-errors";
import { traceTurn } from "./run-trace";
import { syncStateFromTools } from "./state-sync";
import { runSubmittedQuiz } from "./submit-quiz";
import { toSupervisorState } from "./supervisor-state";
import { closeLostToolCalls, repairToolHistory } from "./tool-history";

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
 * `forwardedProps.settings` and the user's API key (`config.apiKey`), builds an inner agent for the OpenAI model, passes it a trimmed state and pipes its events through,
 * adding a `STATE_DELTA` for each subagent tool result and a result for any
 * server tool call the AI SDK rejected (see `tool-history.ts`). A tool's chat
 * card is its only reply: text after a successful card tool is dropped (see
 * `card-replies.ts`). Subagent
 * output and Board views stream to the canvas as drafts while they are
 * written (see `drafts.ts`). A quiz Submit
 * (`forwardedProps.a2uiAction`) is graded in code; the Supervisor runs only
 * to explain a failed grading. A failed
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
      this.config.apiKey,
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
    const drafts = new Subject<Draft>();

    const ctx: SupervisorRunContext = {
      settings,
      getState: () => current,
      signal: this.abortController.signal,
      env,
      answerKeys:
        this.config.answerKeys ??
        new SealedAnswerKeyStore(env[QUIZ_SEAL_SECRET_ENV_KEY]),
      reportDraft: throttleDrafts((draft) => drafts.next(draft)),
    };

    const inner = new BuiltInAgent({
      model: createLanguageModel(settings.apiKey, "supervisor"),
      providerOptions: OPENAI_CALL_OPTIONS,
      maxSteps: this.config.maxSteps ?? SUPERVISOR_MAX_STEPS,
      prompt: this.config.prompt,
      tools: this.config.tools?.(ctx) ?? [],
    });
    this.inner = inner;

    // The Supervisor sees the trimmed state as of when it starts, a history
    // in which every tool call has a result, and no generic A2UI context.
    const runSupervisor = (messages: Message[]) =>
      inner.run({
        ...input,
        messages: repairToolHistory(messages),
        context: dropA2UIContext(input.context),
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

    return traceTurn(
      input,
      events.pipe(
        filter((event) => !isInnerStateEvent(event)),
        muteRepliesAfterCards(input.messages),
        closeLostToolCalls(
          new Set(input.tools.map(({ name }) => name)),
          ctx.signal,
        ),
        // Drafts are reported while a tool runs, so they end with the run.
        finalize(() => drafts.complete()),
        mergeWith(drafts.pipe(map(toStageDraftEvent))),
        streamBoardDrafts(),
        syncStateFromTools(initial, (next) => {
          current = next;
        }),
        explainRunErrors(formatOpenAIError),
      ),
      submit ? QUIZ_SUBMIT_TURN : undefined,
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
