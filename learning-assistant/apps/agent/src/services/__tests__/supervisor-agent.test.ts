import {
  EventType,
  type RunAgentInput,
  type TextMessageContentEvent,
} from "@ag-ui/client";
import { API_KEY_ROUTE } from "@repo/shared/constants/routes";
import { firstValueFrom, toArray } from "rxjs";
import { describe, expect, it } from "vitest";

import { LearningSupervisorAgent } from "../supervisor-agent";

const input: RunAgentInput = {
  threadId: "t1",
  runId: "r1",
  state: {},
  messages: [],
  tools: [],
  context: [],
  forwardedProps: {},
};

describe("LearningSupervisorAgent", () => {
  it("explains in chat, then emits RUN_ERROR, when no API key is saved", async () => {
    const agent = new LearningSupervisorAgent({ env: {} });
    const events = await firstValueFrom(agent.run(input).pipe(toArray()));

    expect(events.map((e) => e.type)).toEqual([
      EventType.RUN_STARTED,
      EventType.TEXT_MESSAGE_START,
      EventType.TEXT_MESSAGE_CONTENT,
      EventType.TEXT_MESSAGE_END,
      EventType.RUN_ERROR,
    ]);
    const content = events.find(
      (e): e is TextMessageContentEvent =>
        e.type === EventType.TEXT_MESSAGE_CONTENT,
    );
    expect(content?.delta).toContain(API_KEY_ROUTE);
  });

  it("keeps its config when cloned", async () => {
    const agent = new LearningSupervisorAgent({ env: {} });
    const clone = agent.clone();

    expect(clone).toBeInstanceOf(LearningSupervisorAgent);
    const events = await firstValueFrom(clone.run(input).pipe(toArray()));
    expect(events.at(-1)?.type).toBe(EventType.RUN_ERROR);
  });
});
