import {
  type BaseEvent,
  EventType,
  type StateSnapshotEvent,
} from "@ag-ui/client";
import { filter, map, type OperatorFunction, pipe, takeWhile } from "rxjs";

import { CLIENT_VISIBLE_STATE_KEYS } from "../../constants/graph";
import { formatOpenAIError } from "../../utils/openai-errors";
import { explainRunErrors } from "../run-errors";

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
 * at every step of the graph, changed or not.
 */
const dropRepeatedSnapshots = (): OperatorFunction<BaseEvent, BaseEvent> => {
  let lastSnapshot: string | undefined;

  return filter((event) => {
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
 * Turns `LangGraphAgent`'s events into what the browser may receive.
 *
 * The adapter attaches the graph's own event to each one (`rawEvent`) and
 * also sends every graph event as `RAW`. Together they carry the whole graph
 * state and every model input, server-only keys included, so both are
 * removed. A failed run gets a readable message in the chat, and ends at its
 * `RUN_ERROR`: the adapter goes on to send snapshots and `RUN_FINISHED`,
 * which the AG-UI protocol does not allow after an error.
 */
export const toClientEvents = (): OperatorFunction<BaseEvent, BaseEvent> =>
  pipe(
    filter(({ type }) => type !== EventType.RAW),
    map(({ rawEvent: _rawEvent, ...event }: GraphBackedEvent) => event),
    map((event) => (isStateSnapshot(event) ? toVisibleSnapshot(event) : event)),
    dropRepeatedSnapshots(),
    explainRunErrors(formatOpenAIError),
    takeWhile(({ type }) => type !== EventType.RUN_ERROR, true),
  );
