import {
  AIMessage,
  type BaseMessage,
  HumanMessage,
  ToolMessage,
} from "@langchain/core/messages";
import { describe, expect, it } from "vitest";

import { A2UI_ACTION_TOOL } from "../../constants/graph";
import {
  estimateTokens,
  findSummaryCut,
  findUnsummarized,
  formatTranscript,
  planSummary,
} from "../conversation-summary";

const LONG = "x".repeat(400);

const human = (id: string, text = LONG) =>
  new HumanMessage({ id, content: text });

const reply = (id: string, text = LONG) => new AIMessage({ id, content: text });

const call = (id: string, callId: string, name = "research") =>
  new AIMessage({
    id,
    content: "",
    tool_calls: [{ id: callId, name, args: { topic: "closures" } }],
  });

const result = (id: string, callId: string, name = "research") =>
  new ToolMessage({
    id,
    tool_call_id: callId,
    name,
    content: '{"ok":true}',
  });

/** Four turns: a question and a reply each, the second one using a tool. */
const THREAD: BaseMessage[] = [
  human("h1"),
  reply("a1"),
  human("h2"),
  call("c2", "call_2"),
  result("t2", "call_2"),
  reply("a2"),
  human("h3"),
  reply("a3"),
  human("h4"),
  reply("a4"),
];

const LIMITS = { triggerTokens: 500, keepTurns: 2 };

const idsOf = (messages: BaseMessage[]) => messages.map(({ id }) => id);

/** Every tool call and its result are on the same side of `cut`. */
const keepsToolCallsWhole = (messages: BaseMessage[], cut: number) =>
  messages.every((message, index) => {
    if (!ToolMessage.isInstance(message)) {
      return true;
    }
    const callIndex = messages.findIndex(
      (other) =>
        AIMessage.isInstance(other) &&
        (other.tool_calls ?? []).some(({ id }) => id === message.tool_call_id),
    );
    return callIndex < cut === index < cut;
  });

describe("findUnsummarized", () => {
  it("is the messages after the last one summarised", () => {
    expect(idsOf(findUnsummarized(THREAD, "a2"))).toEqual([
      "h3",
      "a3",
      "h4",
      "a4",
    ]);
  });

  it("is every message before the first summary, or when the id is gone", () => {
    expect(findUnsummarized(THREAD, null)).toHaveLength(THREAD.length);
    expect(findUnsummarized(THREAD, "missing")).toHaveLength(THREAD.length);
  });
});

describe("estimateTokens", () => {
  it("counts text and tool call arguments", () => {
    expect(estimateTokens([human("h", "abcd")])).toBe(1);
    expect(estimateTokens([call("c", "call")])).toBe(
      Math.ceil(JSON.stringify({ topic: "closures" }).length / 4),
    );
  });
});

describe("findSummaryCut", () => {
  it("cuts at the start of a turn and keeps the last turns whole", () => {
    expect(findSummaryCut(THREAD, 2)).toBe(6);
    expect(findSummaryCut(THREAD, 1)).toBe(8);
  });

  it("is 0 when every turn must stay", () => {
    expect(findSummaryCut(THREAD, 4)).toBe(0);
  });

  it("never separates a tool call from its result", () => {
    // A card the student answered only after writing again.
    const open = [
      human("h1"),
      call("c1", "card"),
      human("h2"),
      result("t1", "card", "showConceptCard"),
      reply("a2"),
      human("h3"),
      reply("a3"),
    ];

    const cut = findSummaryCut(open, 1);
    expect(cut).not.toBe(2);
    expect(keepsToolCallsWhole(open, cut)).toBe(true);
    for (const keepTurns of [1, 2, 3]) {
      expect(
        keepsToolCallsWhole(THREAD, findSummaryCut(THREAD, keepTurns)),
      ).toBe(true);
    }
  });
});

describe("planSummary", () => {
  it("waits until the messages after the summary pass the budget", () => {
    expect(
      planSummary(THREAD, null, { ...LIMITS, triggerTokens: 100_000 }),
    ).toBeNull();
  });

  it("folds everything before the turns it keeps", () => {
    const plan = planSummary(THREAD, null, LIMITS);

    expect(plan?.upTo).toBe("a2");
    expect(idsOf(plan?.fold ?? [])).toEqual(idsOf(THREAD.slice(0, 6)));
  });

  it("folds nothing more when rerun right after a fold", () => {
    const plan = planSummary(THREAD, null, LIMITS);

    expect(planSummary(THREAD, plan?.upTo ?? null, LIMITS)).toBeNull();
  });

  it("folds only what came after the last summary", () => {
    const plan = planSummary(
      [...THREAD, human("h5"), reply("a5")],
      "a2",
      LIMITS,
    );

    expect(idsOf(plan?.fold ?? [])).toEqual(["h3", "a3"]);
    expect(plan?.upTo).toBe("a3");
  });

  it("never changes the messages it plans for", () => {
    const before = JSON.stringify(THREAD);
    planSummary(THREAD, null, LIMITS);
    expect(JSON.stringify(THREAD)).toBe(before);
  });
});

describe("formatTranscript", () => {
  it("names who said what and which tools were used", () => {
    const text = formatTranscript([
      human("h", "teach me closures"),
      call("c", "call_1"),
      result("t", "call_1"),
      reply("a", "Done."),
    ]);

    expect(text).toBe(
      [
        "Student: teach me closures",
        'Assistant used research: {"topic":"closures"}',
        'Result of research: {"ok":true}',
        "Assistant: Done.",
      ].join("\n"),
    );
  });

  it("leaves out a surface action and its answers", () => {
    const text = formatTranscript([
      new AIMessage({
        id: "c",
        content: "",
        tool_calls: [
          {
            id: "action",
            name: A2UI_ACTION_TOOL,
            args: { answers: { q1: 2 } },
          },
        ],
      }),
      result("t", "action", A2UI_ACTION_TOOL),
    ]);

    expect(text).toBe("");
  });

  it("cuts a long message short", () => {
    expect(
      formatTranscript([human("h", "y".repeat(5000))]).length,
    ).toBeLessThan(1000);
  });
});
