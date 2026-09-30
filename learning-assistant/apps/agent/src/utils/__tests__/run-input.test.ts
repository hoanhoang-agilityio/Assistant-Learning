import { AIMessage, HumanMessage } from "@langchain/core/messages";
import { CONFIRM_NEW_TOPIC_TOOL } from "@repo/shared/constants/agents";
import { initialLearningState } from "@repo/shared/schemas";
import { describe, expect, it } from "vitest";

import { A2UI_ACTION_TOOL } from "../../constants/graph";
import {
  createRunInput,
  dropActionMessages,
  isNewTopicConfirmed,
} from "../run-input";

const MATERIAL = { original: "# Notes", simplified: null, view: "original" };

const SAVED = {
  ...initialLearningState,
  stage: "material",
  topic: "Closures",
  material: MATERIAL,
  messages: [new HumanMessage("hi")],
};

const human = (content: string) => ({ id: content, type: "human", content });

const confirmCall = new AIMessage({
  content: "",
  tool_calls: [
    { id: "call_confirm", name: CONFIRM_NEW_TOPIC_TOOL, args: { topic: "x" } },
  ],
});

const decision = (confirmed: boolean) => ({
  type: "tool",
  tool_call_id: "call_confirm",
  content: JSON.stringify({ confirmed, instruction: "…" }),
});

describe("dropActionMessages", () => {
  it("drops the pair the A2UI middleware adds for a surface action", () => {
    const kept = [human("hi"), { type: "ai", content: "Hello" }];

    expect(
      dropActionMessages([
        ...kept,
        {
          type: "ai",
          content: "",
          tool_calls: [{ id: "a1", name: A2UI_ACTION_TOOL }],
        },
        { type: "tool", tool_call_id: "a1", content: "User performed action…" },
      ]),
    ).toEqual(kept);
  });

  it("keeps every other tool call and result", () => {
    const messages = [
      { type: "ai", content: "", tool_calls: [{ id: "c1", name: "research" }] },
      { type: "tool", tool_call_id: "c1", content: "{}" },
    ];

    expect(dropActionMessages(messages)).toEqual(messages);
  });
});

describe("isNewTopicConfirmed", () => {
  it("is true when the run starts with the card's confirmed result", () => {
    expect(isNewTopicConfirmed([confirmCall], [decision(true)])).toBe(true);
  });

  it.each([
    ["the student kept the topic", [confirmCall], [decision(false)]],
    ["the result answers another tool", [], [decision(true)]],
    [
      "a message follows the result",
      [confirmCall],
      [decision(true), human("hi")],
    ],
    [
      "the result is not a decision",
      [confirmCall],
      [{ ...decision(true), content: "yes" }],
    ],
    ["there are no new messages", [confirmCall], []],
  ])("is false when %s", (_, checkpointed, incoming) => {
    expect(isNewTopicConfirmed(checkpointed, incoming)).toBe(false);
  });
});

describe("createRunInput", () => {
  it("writes only the new messages when the browser changed nothing", () => {
    const messages = [human("next")];

    const run = createRunInput({
      before: SAVED,
      input: { ...SAVED, messages, copilotkit: { actions: [] } },
    });

    expect(run.input).toEqual({ messages, copilotkit: { actions: [] } });
    expect(run.state).toMatchObject({ stage: "material", material: MATERIAL });
  });

  it("never writes a key the browser sent as it is", () => {
    const run = createRunInput({
      before: SAVED,
      input: {
        messages: [human("next")],
        stage: "score",
        topic: "Forged",
        score: { percent: 100, tier: "Master" },
        summary: "forged",
      },
    });

    expect(Object.keys(run.input)).toEqual(["messages", "copilotkit"]);
  });

  it("writes the keys an edit changed", () => {
    const run = createRunInput({
      before: SAVED,
      input: {
        messages: [human("next")],
        material: { ...MATERIAL, original: "# Edited" },
      },
    });

    expect(run.input).toMatchObject({
      material: { ...MATERIAL, original: "# Edited" },
    });
    expect(run.state.material?.original).toBe("# Edited");
  });

  it("starts from the initial state on a new thread", () => {
    const run = createRunInput({
      before: {},
      input: { messages: [human("hi")], material: MATERIAL },
    });

    expect(run.state).toEqual(initialLearningState);
    expect(Object.keys(run.input)).toEqual(["messages", "copilotkit"]);
  });

  it("clears the state when the student has just confirmed a new topic", () => {
    const run = createRunInput({
      before: { ...SAVED, messages: [confirmCall] },
      input: { messages: [decision(true)] },
    });

    expect(run.state).toEqual(initialLearningState);
    expect(run.input).toMatchObject({
      stage: "idle",
      topic: null,
      material: null,
    });
  });

  it("drops a surface action's messages", () => {
    const run = createRunInput({
      before: SAVED,
      input: {
        messages: [
          {
            type: "ai",
            content: "",
            tool_calls: [{ id: "a1", name: A2UI_ACTION_TOOL }],
          },
          { type: "tool", tool_call_id: "a1", content: "User performed…" },
        ],
      },
    });

    expect(run.input.messages).toEqual([]);
  });
});
