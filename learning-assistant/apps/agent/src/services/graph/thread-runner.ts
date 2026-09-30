import { type BaseEvent, EventType } from "@ag-ui/client";
import type { LangGraphAgent, ProcessedEvents } from "@ag-ui/langgraph";
import {
  type AgentRunnerConnectRequest,
  InMemoryAgentRunner,
} from "@copilotkit/runtime/v2";
import type { BaseCheckpointSaver } from "@langchain/langgraph";
import { concat, defer, EMPTY, Observable, type Subscriber, tap } from "rxjs";

import { NO_API_KEY, RELOAD_RUN_ID } from "../../constants/graph";
import { createChatModel } from "../llm/chat-model";
import { threadCheckpointer } from "./checkpointer";
import { toClientEvents } from "./client-events";
import { createGraphAgent } from "./learning-agent";
import { createLearningGraph } from "./learning-graph";

/**
 * The one private `LangGraphAgent` method this file calls: it emits a
 * thread's state and messages as snapshots, converted and cut down to the
 * keys the browser may see exactly as at the end of a run.
 */
interface SnapshotSource {
  getStateAndMessagesSnapshots(threadId: string): Promise<void>;
}

/**
 * The runtime's in-memory runner, plus reload from the checkpoint. The stock
 * runner answers `/connect` by replaying events it holds in process memory,
 * so after a restart (or on another instance) an existing thread comes back
 * blank. When it has nothing to replay, this one rebuilds the thread's
 * messages and state from the checkpoint instead.
 */
export class LearningThreadRunner extends InMemoryAgentRunner {
  private checkpointer: BaseCheckpointSaver;

  constructor(checkpointer: BaseCheckpointSaver = threadCheckpointer) {
    super();
    this.checkpointer = checkpointer;
  }

  connect(request: AgentRunnerConnectRequest): Observable<BaseEvent> {
    let isReplayed = false;

    return concat(
      super.connect(request).pipe(
        tap(() => {
          isReplayed = true;
        }),
      ),
      defer(() =>
        isReplayed ? EMPTY : this.replayCheckpoint(request.threadId),
      ),
    );
  }

  /** A graph agent that only reads: its model and user are never used. */
  private createReader(): LangGraphAgent {
    const graph = createLearningGraph({
      model: createChatModel(NO_API_KEY),
      checkpointer: this.checkpointer,
    });
    return createGraphAgent(graph, RELOAD_RUN_ID);
  }

  /** The thread's checkpoint as one finished run, or nothing without one. */
  private replayCheckpoint(threadId: string): Observable<BaseEvent> {
    return new Observable<ProcessedEvents>((subscriber) => {
      this.emitCheckpoint(threadId, subscriber).then(
        () => subscriber.complete(),
        (error: unknown) => subscriber.error(error),
      );
    }).pipe(toClientEvents());
  }

  private async emitCheckpoint(
    threadId: string,
    subscriber: Subscriber<ProcessedEvents>,
  ): Promise<void> {
    const checkpoint = await this.checkpointer.getTuple({
      configurable: { thread_id: threadId },
    });
    if (!checkpoint) {
      return;
    }

    const reader = this.createReader();
    reader.assistant = await reader.getAssistant();
    reader.activeRun = {
      id: RELOAD_RUN_ID,
      threadId,
      schemaKeys: await reader.getSchemaKeys(),
    };
    reader.subscriber = subscriber;

    const run = { threadId, runId: RELOAD_RUN_ID };
    subscriber.next({ type: EventType.RUN_STARTED, ...run });
    await (reader as unknown as SnapshotSource).getStateAndMessagesSnapshots(
      threadId,
    );
    subscriber.next({ type: EventType.RUN_FINISHED, ...run });
  }
}
