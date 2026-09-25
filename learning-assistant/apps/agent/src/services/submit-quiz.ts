import {
  type BaseEvent,
  EventType,
  type Message,
  type RunAgentInput,
  type RunFinishedEvent,
  type RunStartedEvent,
  type ToolCallArgsEvent,
  type ToolCallEndEvent,
  type ToolCallResultEvent,
  type ToolCallStartEvent,
} from "@ag-ui/client";
import type { QuizSubmission, SubagentTool } from "@repo/shared/schemas";
import { concat, concatMap, defer, filter, type Observable, of } from "rxjs";

import type { SupervisorRunContext } from "../types/agents";
import { runEvaluateStep } from "./tools/quiz-tools";

const EVALUATE_TOOL: SubagentTool = "evaluate";
const EVALUATE_ARGS = "{}";

interface SubmittedQuizParams {
  input: RunAgentInput;
  ctx: SupervisorRunContext;
  submission?: QuizSubmission;
  /** Runs the Supervisor LLM on `messages` with the state as of now. */
  runSupervisor: (messages: Message[]) => Observable<BaseEvent>;
}

/**
 * A Submit press. The quiz is graded in code first, as an `evaluate` tool call
 * the wrapper makes itself (so the chat shows its progress card and the state
 * sync writes the result like any other tool). Its card is the whole reply:
 * the Supervisor runs, with that call in its history, only to explain a
 * failed grading. The LLM never decides whether to grade.
 */
export const runSubmittedQuiz = ({
  input,
  ctx,
  submission,
  runSupervisor,
}: SubmittedQuizParams): Observable<BaseEvent> => {
  const toolCallId = crypto.randomUUID();
  const parentMessageId = crypto.randomUUID();

  const started: RunStartedEvent = {
    type: EventType.RUN_STARTED,
    threadId: input.threadId,
    runId: input.runId,
  };
  const toolStart: ToolCallStartEvent = {
    type: EventType.TOOL_CALL_START,
    toolCallId,
    toolCallName: EVALUATE_TOOL,
    parentMessageId,
  };
  const toolArgs: ToolCallArgsEvent = {
    type: EventType.TOOL_CALL_ARGS,
    toolCallId,
    delta: EVALUATE_ARGS,
  };
  const toolEnd: ToolCallEndEvent = {
    type: EventType.TOOL_CALL_END,
    toolCallId,
  };

  const finished: RunFinishedEvent = {
    type: EventType.RUN_FINISHED,
    threadId: input.threadId,
    runId: input.runId,
  };

  const toResultEvents = (
    ok: boolean,
    content: string,
  ): Observable<BaseEvent> => {
    const result: ToolCallResultEvent = {
      type: EventType.TOOL_CALL_RESULT,
      messageId: crypto.randomUUID(),
      toolCallId,
      content,
      role: "tool",
    };
    if (ok) {
      return of(result, finished);
    }
    const messages: Message[] = [
      ...input.messages,
      {
        id: parentMessageId,
        role: "assistant",
        toolCalls: [
          {
            id: toolCallId,
            type: "function",
            function: { name: EVALUATE_TOOL, arguments: EVALUATE_ARGS },
          },
        ],
      },
      { id: result.messageId, role: "tool", toolCallId, content },
    ];

    // `defer` starts the Supervisor only after the result event has passed
    // through the state sync, so it sees the graded state. Its own
    // RUN_STARTED is dropped: this run already started.
    return concat(
      of(result),
      defer(() => runSupervisor(messages)).pipe(
        filter((event) => event.type !== EventType.RUN_STARTED),
      ),
    );
  };

  return concat(
    of(started, toolStart, toolArgs, toolEnd),
    defer(() => runEvaluateStep(ctx, submission)).pipe(
      concatMap((result) => toResultEvents(result.ok, JSON.stringify(result))),
    ),
  );
};
