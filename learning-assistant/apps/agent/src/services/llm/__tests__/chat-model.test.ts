import { AIMessageChunk } from "@langchain/core/messages";
import { ChatGenerationChunk } from "@langchain/core/outputs";
import { describe, expect, it } from "vitest";

import { withResponseId } from "../chat-model";

const chunk = (id?: string) =>
  new ChatGenerationChunk({
    text: "",
    message: new AIMessageChunk({ content: "", id }),
  });

async function* streamOf(chunks: ChatGenerationChunk[]) {
  yield* chunks;
}

const idsOf = async (chunks: ChatGenerationChunk[]) => {
  const ids: (string | undefined)[] = [];
  for await (const { message } of withResponseId(streamOf(chunks))) {
    ids.push(message.id);
  }
  return ids;
};

describe("withResponseId", () => {
  it("names every chunk after the response", async () => {
    expect(
      await idsOf([chunk("resp_1"), chunk(), chunk(), chunk("resp_1")]),
    ).toEqual(["resp_1", "resp_1", "resp_1", "resp_1"]);
  });

  it("leaves the chunks before the first id alone", async () => {
    expect(await idsOf([chunk(), chunk("resp_1"), chunk()])).toEqual([
      undefined,
      "resp_1",
      "resp_1",
    ]);
  });
});
