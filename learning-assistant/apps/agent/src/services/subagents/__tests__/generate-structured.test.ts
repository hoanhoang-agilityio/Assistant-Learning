import { beforeEach, describe, expect, it, vi } from "vitest";
import { z } from "zod";

import { SILENT_RUN_METADATA } from "../../../constants/openai";
import { ScriptedModel } from "../../llm/__tests__/scripted-model";
import { createChatModel } from "../../llm/chat-model";
import { generateStructured } from "../generate-structured";

vi.mock("../../llm/chat-model", () => ({ createChatModel: vi.fn() }));

const schema = z.object({ title: z.string(), markdown: z.string() });

const params = {
  settings: { apiKey: "sk-test" } as never,
  system: "system",
  prompt: "prompt",
  schema,
};

const WHOLE = { title: "Closures", markdown: "# Closures\nA function…" };

/** Makes `generateStructured` call a model that streams `reply`. */
const replyWith = (reply: string): ScriptedModel => {
  const model = new ScriptedModel(() => ({ text: reply }));
  vi.mocked(createChatModel).mockReturnValue(model as never);
  return model;
};

beforeEach(() => {
  vi.mocked(createChatModel).mockReset();
});

describe("generateStructured", () => {
  it("returns the validated whole without onPartial", async () => {
    replyWith(JSON.stringify(WHOLE));

    await expect(generateStructured(params)).resolves.toEqual(WHOLE);
    expect(createChatModel).toHaveBeenCalledWith("sk-test");
  });

  it("reports the object as it grows and returns the whole", async () => {
    replyWith(JSON.stringify(WHOLE));
    const onPartial = vi.fn();

    await expect(generateStructured({ ...params, onPartial })).resolves.toEqual(
      WHOLE,
    );

    const partials = onPartial.mock.calls.map(([partial]) => partial);
    expect(partials.length).toBeGreaterThan(2);
    expect(partials[0]).toEqual({});
    expect(partials).toContainEqual({ title: "Closures" });
    expect(partials.at(-1)).toEqual(WHOLE);
  });

  it("asks for the schema's JSON and keeps the call out of the chat", async () => {
    const model = replyWith(JSON.stringify(WHOLE));
    const { signal } = new AbortController();

    await generateStructured({ ...params, signal });

    const [call] = model.calls;
    expect(call?.messages.map((message) => message.text)).toEqual([
      "system",
      "prompt",
    ]);
    expect(call?.options).toMatchObject({
      response_format: {
        type: "json_schema",
        json_schema: {
          strict: true,
          schema: {
            type: "object",
            required: ["title", "markdown"],
            additionalProperties: false,
          },
        },
      },
    });
    expect(call?.options.signal).toBeDefined();
    expect(model.calls).toHaveLength(1);
  });

  it("marks the call silent in its run metadata", async () => {
    const model = replyWith(JSON.stringify(WHOLE));
    const stream = vi.spyOn(model, "stream");

    await generateStructured(params);

    expect(stream.mock.calls[0]?.[1]).toMatchObject({
      metadata: SILENT_RUN_METADATA,
    });
  });

  it("rejects a reply that does not match the schema", async () => {
    replyWith(JSON.stringify({ title: "Closures" }));

    await expect(generateStructured(params)).rejects.toThrow(z.ZodError);
  });

  it("rejects a reply that was cut short", async () => {
    replyWith('{"title":"Closures","markdown":"# Clo');
    const onPartial = vi.fn();

    await expect(generateStructured({ ...params, onPartial })).rejects.toThrow(
      SyntaxError,
    );
    expect(onPartial).toHaveBeenCalled();
  });

  it("throws the provider's own error", async () => {
    const providerError = new Error("Incorrect API key provided");
    const model = replyWith("");
    vi.spyOn(model, "stream").mockRejectedValue(providerError);

    await expect(generateStructured(params)).rejects.toBe(providerError);
  });

  it("stops when the signal is aborted", async () => {
    replyWith(JSON.stringify(WHOLE));
    const controller = new AbortController();
    controller.abort();

    await expect(
      generateStructured({ ...params, signal: controller.signal }),
    ).rejects.toThrow();
  });
});
