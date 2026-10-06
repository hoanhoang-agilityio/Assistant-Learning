import { AUTO_TITLE_MAX_LENGTH } from "@repo/shared/constants/conversations";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { TITLE_INPUT_MAX_CHARS } from "../../../constants/memory";
import {
  type ScriptedCall,
  ScriptedModel,
} from "../../llm/__tests__/scripted-model";
import { createChatModel } from "../../llm/chat-model";
import { summarizeTitle } from "../summarize-title";

vi.mock("../../llm/chat-model", () => ({ createChatModel: vi.fn() }));

const API_KEY = "sk-title-test";

/** Makes the model answer `{ title }` and returns the calls it gets. */
const replyWith = (title: string): ScriptedCall[] => {
  const calls: ScriptedCall[] = [];
  vi.mocked(createChatModel).mockReturnValue(
    new ScriptedModel((_messages, call) => {
      calls.push(call);
      return { text: JSON.stringify({ title }) };
    }) as never,
  );
  return calls;
};

beforeEach(() => {
  vi.mocked(createChatModel).mockReset();
});

describe("summarizeTitle", () => {
  it("names the conversation from the first message, with the user's key", async () => {
    const calls = replyWith("JavaScript closures");

    const title = await summarizeTitle({
      apiKey: API_KEY,
      userText: "Can you teach me how closures work in JavaScript?",
    });

    expect(title).toBe("JavaScript closures");
    expect(createChatModel).toHaveBeenCalledWith(API_KEY);
    expect(calls[0]?.messages.at(-1)?.text).toContain(
      "how closures work in JavaScript",
    );
  });

  it("drops quotes and ending punctuation, and cuts a long title", async () => {
    replyWith('"Closures."');
    expect(await summarizeTitle({ apiKey: API_KEY, userText: "x" })).toBe(
      "Closures",
    );

    replyWith("word ".repeat(40));
    const long = await summarizeTitle({ apiKey: API_KEY, userText: "x" });
    expect(long.length).toBeLessThanOrEqual(AUTO_TITLE_MAX_LENGTH);
  });

  it("reads only the start of a very long message", async () => {
    const calls = replyWith("Essay");

    await summarizeTitle({
      apiKey: API_KEY,
      userText: `${"a".repeat(TITLE_INPUT_MAX_CHARS)}TAIL`,
    });

    expect(calls[0]?.messages.at(-1)?.text).not.toContain("TAIL");
  });

  it("fails when the title is empty", async () => {
    replyWith(' "" ');
    await expect(
      summarizeTitle({ apiKey: API_KEY, userText: "hi" }),
    ).rejects.toThrow();
  });
});
