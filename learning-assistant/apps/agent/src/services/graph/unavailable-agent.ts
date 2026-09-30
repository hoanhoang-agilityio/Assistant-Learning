import {
  AbstractAgent,
  type BaseEvent,
  EventType,
  type RunAgentInput,
  type RunErrorEvent,
  type RunStartedEvent,
} from "@ag-ui/client";
import { type Observable, of } from "rxjs";

import { explainRunErrors } from "../run-errors";

/**
 * An agent that cannot run: every run ends at once with `reason` as a
 * readable message in the chat, then `RUN_ERROR`.
 */
export class UnavailableAgent extends AbstractAgent {
  private reason: string;

  constructor(reason: string) {
    super();
    this.reason = reason;
  }

  run({ threadId, runId }: RunAgentInput): Observable<BaseEvent> {
    const started: RunStartedEvent = {
      type: EventType.RUN_STARTED,
      threadId,
      runId,
    };
    const failed: RunErrorEvent = {
      type: EventType.RUN_ERROR,
      message: this.reason,
    };
    return of(started, failed).pipe(explainRunErrors((message) => message));
  }

  // The runtime clones the agent for each request, and the base clone does
  // not copy subclass fields.
  clone(): UnavailableAgent {
    const cloned: UnavailableAgent = super.clone();
    cloned.reason = this.reason;
    return cloned;
  }
}
