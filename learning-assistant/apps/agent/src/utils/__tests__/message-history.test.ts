import { AIMessage, HumanMessage, ToolMessage } from "@langchain/core/messages";
import { describe, expect, it } from "vitest";

import { UNANSWERED_TOOL_RESULT } from "../../constants/errors";
import { answerOpenToolCalls, isToolSuccess } from "../message-history";

const call = (id: string, name = "research") =>
  new AIMessage({ content: "", tool_calls: [{ id, name, args: {} }] });

const result = (id: string, content = '{"ok":true}') =>
  new ToolMessage({ tool_call_id: id, content });

describe("answerOpenToolCalls", () => {
  it("adds a result right after a tool call that has none", () => {
    const messages = [
      new HumanMessage("research"),
      call("c1"),
      new HumanMessage("hi"),
    ];

    const repaired = answerOpenToolCalls(messages);

    expect(repaired.map((message) => message.type)).toEqual([
      "human",
      "ai",
      "tool",
      "human",
    ]);
    expect(repaired[2]).toMatchObject({ tool_call_id: "c1", name: "research" });
    expect(repaired[2]?.text).toContain(UNANSWERED_TOOL_RESULT);
  });

  it("leaves an answered history as it is", () => {
    const messages = [call("c1"), result("c1"), new AIMessage("Done.")];

    expect(answerOpenToolCalls(messages)).toEqual(messages);
  });

  it("answers only the calls of a message that are still open", () => {
    const both = new AIMessage({
      content: "",
      tool_calls: [
        { id: "c1", name: "research", args: {} },
        { id: "c2", name: "setTheme", args: {} },
      ],
    });

    const repaired = answerOpenToolCalls([both, result("c1")]);

    expect(
      repaired.map((message) =>
        ToolMessage.isInstance(message) ? message.tool_call_id : "ai",
      ),
    ).toEqual(["ai", "c2", "c1"]);
  });
});

describe("isToolSuccess", () => {
  it.each([
    ['{"ok":true,"data":{}}', true],
    ["Theme is now dark.", true],
    ['{"ok":false,"error":"No quiz."}', false],
  ])("%s → %s", (content, expected) => {
    expect(isToolSuccess(result("c1", content))).toBe(expected);
  });
});
