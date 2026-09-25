import { type BaseEvent, EventType } from "@ag-ui/client";
import { describe, expect, it } from "vitest";

import { AGENT_EVENT_LOG_MAX_TEXT } from "@/constants/agent-event-log";
import {
  describeAgentEvent,
  formatElapsed,
  formatEventLine,
} from "@/utils/agent-event-log";

const toolStart = {
  type: EventType.TOOL_CALL_START,
  toolCallId: "call-1",
  toolCallName: "renderSurface",
} as BaseEvent;

describe("describeAgentEvent", () => {
  it("names the tool a call starts", () => {
    expect(describeAgentEvent(toolStart)).toBe("renderSurface");
  });

  it("lists the operations of a state delta", () => {
    const event = {
      type: EventType.STATE_DELTA,
      delta: [
        { op: "replace", path: "/stage", value: "quiz" },
        { op: "add", path: "/quiz", value: {} },
      ],
    } as BaseEvent;

    expect(describeAgentEvent(event)).toBe("replace /stage, add /quiz");
  });

  it("cuts a long tool result", () => {
    const event = {
      type: EventType.TOOL_CALL_RESULT,
      messageId: "m-1",
      toolCallId: "call-1",
      content: "x".repeat(AGENT_EVENT_LOG_MAX_TEXT + 20),
    } as BaseEvent;

    expect(describeAgentEvent(event)).toBe(
      `${"x".repeat(AGENT_EVENT_LOG_MAX_TEXT)}…`,
    );
  });

  it("has nothing to add for a run start", () => {
    const event = {
      type: EventType.RUN_STARTED,
      threadId: "t-1",
      runId: "r-1",
    } as BaseEvent;

    expect(describeAgentEvent(event)).toBe("");
  });
});

describe("formatElapsed", () => {
  it("rounds to whole milliseconds", () => {
    expect(formatElapsed(1234.6)).toBe("+1235ms");
  });
});

describe("formatEventLine", () => {
  it("joins prefix, time, type and detail", () => {
    expect(formatEventLine(toolStart, 12)).toBe(
      "[ag-ui] +12ms TOOL_CALL_START renderSurface",
    );
  });

  it("adds the deltas streamed since the last line", () => {
    const event = {
      type: EventType.TOOL_CALL_END,
      toolCallId: "call-1",
    } as BaseEvent;

    expect(formatEventLine(event, 40, 17)).toBe(
      "[ag-ui] +40ms TOOL_CALL_END (17 streamed)",
    );
  });
});
