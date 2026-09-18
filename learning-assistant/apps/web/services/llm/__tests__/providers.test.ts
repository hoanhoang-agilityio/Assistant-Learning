import { describe, expect, it } from "vitest";

import { getAvailableProviders, hasProviderKey } from "../providers";

describe("getAvailableProviders", () => {
  it("returns nothing when no keys are set", () => {
    expect(getAvailableProviders({})).toEqual([]);
  });

  it("returns only providers with a key, in catalog order", () => {
    expect(
      getAvailableProviders({
        GOOGLE_GENERATIVE_AI_API_KEY: "g",
        OPENAI_API_KEY: "o",
      }),
    ).toEqual(["openai", "google"]);
  });

  it("treats blank keys as missing", () => {
    expect(hasProviderKey("anthropic", { ANTHROPIC_API_KEY: "  " })).toBe(
      false,
    );
  });
});
