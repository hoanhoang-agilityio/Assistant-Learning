import { HumanMessage } from "@langchain/core/messages";
import { initialLearningState } from "@repo/shared/schemas";
import { describe, expect, it } from "vitest";

import { A2UI_ACTION_TOOL } from "../../constants/graph";
import {
  createRunInput,
  dropActionMessages,
  findUserText,
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

  it("never clears the server's work for a browser that sends an empty state", () => {
    const run = createRunInput({
      before: SAVED,
      input: { ...initialLearningState, messages: [human("hi")] },
    });

    expect(run.state).toMatchObject({ stage: "material", material: MATERIAL });
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

describe("findUserText", () => {
  it("is the newest message the student wrote in this run", () => {
    expect(findUserText([human("first"), human("second")], [])).toBe("second");
  });

  it("skips messages the checkpoint already holds", () => {
    const saved = [new HumanMessage({ id: "first", content: "first" })];
    expect(findUserText([human("first")], saved)).toBeNull();
  });

  it("joins the text parts of a message with several", () => {
    const message = {
      id: "m1",
      type: "human",
      content: [
        { type: "text", text: "Teach me" },
        { type: "image_url", image_url: "x" },
        { type: "text", text: "closures" },
      ],
    };
    expect(findUserText([message], [])).toBe("Teach me closures");
  });

  it("is null for a run without a student message", () => {
    expect(findUserText(undefined, [])).toBeNull();
    expect(
      findUserText([{ id: "t", type: "tool", content: "{}" }], []),
    ).toBeNull();
  });
});
