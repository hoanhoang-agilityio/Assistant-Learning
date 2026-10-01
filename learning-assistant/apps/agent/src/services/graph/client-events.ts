import {
  type BaseEvent,
  type CustomEvent,
  EventType,
  type Message,
  type MessagesSnapshotEvent,
  type StateSnapshotEvent,
} from "@ag-ui/client";
import { filter, map, Observable, type OperatorFunction, pipe } from "rxjs";

import {
  CLIENT_VISIBLE_STATE_KEYS,
  MANUAL_STATE_EVENT,
} from "../../constants/graph";
import { formatOpenAIError } from "../../utils/openai-errors";
import { muteCardReplies, muteRepliesAfterCards } from "../card-replies";
import { explainRunErrors } from "../run-errors";
import { streamBoardDrafts } from "./board-drafts";

/** An event as `LangGraphAgent` emits it, with the graph event it came from. */
type GraphBackedEvent = BaseEvent & { rawEvent?: unknown };

const isStateSnapshot = (event: BaseEvent): event is StateSnapshotEvent =>
  event.type === EventType.STATE_SNAPSHOT;

/**
 * The snapshot with only the keys the browser may see. The adapter always
 * adds `messages` (the raw LangChain messages, which the browser gets
 * converted in `MESSAGES_SNAPSHOT`) and `tools` to the keys it was given.
 */
const toVisibleSnapshot = (event: StateSnapshotEvent): StateSnapshotEvent => ({
  ...event,
  snapshot: Object.fromEntries(
    Object.entries(event.snapshot as Record<string, unknown>).filter(([key]) =>
      CLIENT_VISIBLE_STATE_KEYS.includes(key),
    ),
  ),
});

/**
 * Drops a state snapshot equal to the last one sent. The adapter sends one
 * at every step of the graph, changed or not. After a delta the browser's
 * state is no longer the last snapshot, so the next one always goes.
 */
const dropRepeatedSnapshots = (): OperatorFunction<BaseEvent, BaseEvent> => {
  let lastSnapshot: string | undefined;

  return filter((event) => {
    if (event.type === EventType.STATE_DELTA) {
      lastSnapshot = undefined;
      return true;
    }
    if (!isStateSnapshot(event)) {
      return true;
    }
    const snapshot = JSON.stringify(event.snapshot);
    const isRepeated = snapshot === lastSnapshot;
    lastSnapshot = snapshot;
    return !isRepeated;
  });
};

/**
 * The adapter turns a state a tool sends mid-run into a snapshot, and also
 * forwards it as a custom event: the same state twice.
 */
const isManualStateEcho = (event: BaseEvent): boolean =>
  event.type === EventType.CUSTOM &&
  (event as CustomEvent).name === MANUAL_STATE_EVENT;

const SNAPSHOT_EVENTS: readonly string[] = [
  EventType.STATE_SNAPSHOT,
  EventType.MESSAGES_SNAPSHOT,
];

/**
 * Moves a `RUN_ERROR` to the end of the run. The adapter goes on after an
 * error: it sends the thread's saved state and messages, then
 * `RUN_FINISHED`, which the AG-UI protocol does not allow after an error.
 * The snapshots are kept, so the canvas shows what was saved rather than a
 * step that looked like it was still running; everything else after the
 * error is dropped, and the error itself comes last.
 */
const endWithRunError =
  (): OperatorFunction<BaseEvent, BaseEvent> => (source) =>
    new Observable((subscriber) => {
      let failure: BaseEvent | undefined;

      return source.subscribe({
        next: (event) => {
          if (event.type === EventType.RUN_ERROR) {
            failure ??= event;
          } else if (!failure || SNAPSHOT_EVENTS.includes(event.type)) {
            subscriber.next(event);
          }
        },
        error: (error: unknown) => subscriber.error(error),
        complete: () => {
          if (failure) {
            subscriber.next(failure);
          }
          subscriber.complete();
        },
      });
    });

const isMessagesSnapshot = (event: BaseEvent): event is MessagesSnapshotEvent =>
  event.type === EventType.MESSAGES_SNAPSHOT;

/**
 * Turns `LangGraphAgent`'s events into what the browser may receive.
 * `history` is the messages the run started with.
 *
 * - The adapter attaches the graph's own event to each one (`rawEvent`) and
 *   also sends every graph event as `RAW`. Together they carry the whole
 *   graph state and every model input, server-only keys and the quiz's
 *   answers included, so both are removed. So is its copy, as a custom
 *   event, of each state a tool sends mid-run.
 * - A Board view streams to the canvas while the Supervisor writes it (see
 *   `streamBoardDrafts`).
 * - A tool's chat card is its whole reply: text the Supervisor writes after
 *   one succeeds is dropped, from the stream and from message snapshots.
 * - A failed run ends with a readable message in the chat, then its
 *   `RUN_ERROR`.
 */
export const toClientEvents = (
  history: Message[],
): OperatorFunction<BaseEvent, BaseEvent> =>
  pipe(
    filter(
      (event) => event.type !== EventType.RAW && !isManualStateEcho(event),
    ),
    map(({ rawEvent: _rawEvent, ...event }: GraphBackedEvent) => event),
    map((event) => (isStateSnapshot(event) ? toVisibleSnapshot(event) : event)),
    streamBoardDrafts(),
    dropRepeatedSnapshots(),
    muteRepliesAfterCards(history),
    map((event) =>
      isMessagesSnapshot(event)
        ? { ...event, messages: muteCardReplies(event.messages) }
        : event,
    ),
    endWithRunError(),
    explainRunErrors(formatOpenAIError),
  );
