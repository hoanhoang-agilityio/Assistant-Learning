import {
  type BaseEvent,
  EventType,
  type RunAgentInput,
  type RunErrorEvent,
  type TextMessageChunkEvent,
  type TextMessageContentEvent,
} from "@ag-ui/client";
import { LEARNING_AGENT_ID } from "@repo/shared/constants/agents";
import { traceable } from "langsmith/traceable";
import { Observable } from "rxjs";

type ChatMessage = { role: "user" | "assistant"; content: unknown };

interface TurnMessages {
  messages: ChatMessage[];
}

/** The traced call: `messages` are logged as its inputs, `events` are run. */
interface TracedTurn extends TurnMessages {
  events: Observable<BaseEvent>;
}

/** What the student said this turn: their last message, or `action` for a button press. */
const toTurnInputs = (input: RunAgentInput, action?: string): TurnMessages => {
  const content =
    action ??
    input.messages.filter(({ role }) => role === "user").at(-1)?.content;
  return { messages: [{ role: "user", content: content ?? "" }] };
};

/**
 * Runs one turn of the conversation as a single LangSmith trace, tagged with
 * the AG-UI `threadId` so the Threads view groups a conversation's turns. The
 * events are subscribed inside the trace, so every Supervisor step and
 * subagent span of the turn nests under it. `action` stands in for the
 * student's message when a button, not a message, started the turn. A
 * pass-through unless `LANGSMITH_TRACING` is `true`.
 */
export const traceTurn = (
  input: RunAgentInput,
  events: Observable<BaseEvent>,
  action?: string,
): Observable<BaseEvent> =>
  new Observable<BaseEvent>((subscriber) => {
    let stop = () => {};

    const turn = traceable(
      ({ events }: TracedTurn) =>
        new Promise<TurnMessages>((resolve, reject) => {
          if (subscriber.closed) {
            resolve({ messages: [] });
            return;
          }
          let reply = "";
          let failure: string | undefined;
          const outputs = () => ({
            messages: [{ role: "assistant" as const, content: reply }],
          });

          const subscription = events.subscribe({
            next: (event) => {
              if (event.type === EventType.TEXT_MESSAGE_CONTENT) {
                reply += (event as TextMessageContentEvent).delta;
              } else if (event.type === EventType.TEXT_MESSAGE_CHUNK) {
                reply += (event as TextMessageChunkEvent).delta ?? "";
              } else if (event.type === EventType.RUN_ERROR) {
                failure = (event as RunErrorEvent).message;
              }
              subscriber.next(event);
            },
            error: (error: unknown) => {
              subscriber.error(error);
              reject(error);
            },
            complete: () => {
              subscriber.complete();
              if (failure) {
                reject(new Error(failure));
              } else {
                resolve(outputs());
              }
            },
          });
          stop = () => {
            subscription.unsubscribe();
            resolve(outputs());
          };
        }),
      {
        name: LEARNING_AGENT_ID,
        run_type: "chain",
        metadata: { thread_id: input.threadId, run_id: input.runId },
        processInputs: ({ messages }) => ({ messages }),
      },
    );

    // The failure already reached the subscriber; the trace only records it.
    turn({ ...toTurnInputs(input, action), events }).catch(() => {});
    return () => stop();
  });
