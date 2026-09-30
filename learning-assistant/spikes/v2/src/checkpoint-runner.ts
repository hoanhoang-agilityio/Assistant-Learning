import { EventType } from "@ag-ui/client";
import { LangGraphAgent } from "@ag-ui/langgraph";
import { InMemoryAgentRunner } from "@copilotkit/runtime/v2";
import { Observable } from "rxjs";

import { createInProcessClient } from "./inproc-client.ts";

/**
 * Reload after a restart: the stock runner only replays events it holds in
 * memory. When it holds none for the thread, rebuild MESSAGES_SNAPSHOT +
 * STATE_SNAPSHOT from the checkpoint, reusing LangGraphAgent's own converter
 * and output-key filter.
 */
export class CheckpointRunner extends InMemoryAgentRunner {
  constructor(private graph: any, private outputKeys?: string[]) {
    super();
  }
  connect(request: any): Observable<any> {
    return new Observable((sub) => {
      let replayed = 0;
      const inner = super.connect(request).subscribe({
        next: (e) => { replayed++; sub.next(e); },
        error: (e) => sub.error(e),
        complete: async () => {
          if (replayed > 0) return sub.complete();
          const agent = new LangGraphAgent({
            client: createInProcessClient(this.graph, "learning", { trusted: {}, outputKeys: this.outputKeys }) as any,
            graphId: "learning",
            deploymentUrl: "inproc://",
          });
          const a = agent as any;
          a.assistant = await a.getAssistant();
          a.activeRun = { id: "connect", threadId: request.threadId, schemaKeys: await a.getSchemaKeys() };
          a.subscriber = { next: (e: any) => { const { rawEvent: _r, ...rest } = e; sub.next(rest); } };
          sub.next({ type: EventType.RUN_STARTED, threadId: request.threadId, runId: "connect" });
          await a.getStateAndMessagesSnapshots(request.threadId);
          sub.next({ type: EventType.RUN_FINISHED, threadId: request.threadId, runId: "connect" });
          sub.complete();
        },
      });
      return () => inner.unsubscribe();
    });
  }
}
