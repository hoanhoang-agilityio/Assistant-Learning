import { streamText } from "ai";
import { describe, expect, it, vi } from "vitest";
import { z } from "zod";

import { generateStructured } from "../generate-structured";

vi.mock("ai", async (importOriginal) => ({
  ...(await importOriginal<typeof import("ai")>()),
  streamText: vi.fn(),
}));

vi.mock("../../llm/language-model", () => ({
  createLanguageModel: vi.fn(() => ({})),
}));

const schema = z.object({ markdown: z.string() });

const params = {
  settings: { apiKey: "sk-test" } as never,
  system: "system",
  prompt: "prompt",
  schema,
};

const toStream = <T>(items: T[]) =>
  (async function* () {
    yield* items;
  })();

describe("generateStructured with onPartial", () => {
  it("reports each partial object and returns the whole", async () => {
    vi.mocked(streamText).mockReturnValue({
      partialOutputStream: toStream([
        { markdown: "# C" },
        { markdown: "# Cl" },
      ]),
      output: Promise.resolve({ markdown: "# Closures" }),
    } as never);
    const onPartial = vi.fn();

    await expect(generateStructured({ ...params, onPartial })).resolves.toEqual(
      { markdown: "# Closures" },
    );
    expect(onPartial.mock.calls).toEqual([
      [{ markdown: "# C" }],
      [{ markdown: "# Cl" }],
    ]);
  });

  it("throws the provider's error, not the SDK's generic one", async () => {
    const providerError = new Error("Incorrect API key provided");
    vi.mocked(streamText).mockImplementation(((options: {
      onError: (event: { error: unknown }) => void;
    }) => {
      options.onError({ error: providerError });
      const output = Promise.reject(new Error("No output generated."));
      output.catch(() => {});
      return { partialOutputStream: toStream([]), output };
    }) as never);

    await expect(
      generateStructured({ ...params, onPartial: () => {} }),
    ).rejects.toBe(providerError);
  });
});
