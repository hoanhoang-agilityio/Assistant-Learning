import { describe, expect, it } from "vitest";

import type { ProviderErrorKind } from "@/features/agent/types/errors";
import {
  classifyProviderError,
  formatProviderError,
} from "@/features/agent/utils/provider-errors";

const SETTINGS = { provider: "openai", model: "gpt-5.4-mini" } as const;

const createApiError = (message: string, statusCode: number) =>
  Object.assign(new Error(message), { statusCode });

describe("classifyProviderError", () => {
  it.each<[string, unknown, ProviderErrorKind | null]>([
    ["a 401", createApiError("Unauthorized", 401), "auth"],
    [
      "an OpenAI key message",
      new Error("Incorrect API key provided: sk-proj-***abcd."),
      "auth",
    ],
    ["an Anthropic key message", new Error("invalid x-api-key"), "auth"],
    ["a 429", createApiError("Slow down", 429), "rateLimit"],
    [
      "a quota message",
      new Error("You exceeded your current quota"),
      "rateLimit",
    ],
    ["a 404", createApiError("Not Found", 404), "model"],
    [
      "a missing model message",
      new Error("The model `gpt-9` does not exist or you do not have access."),
      "model",
    ],
    ["a 529", createApiError("Overloaded", 529), "overloaded"],
    ["a network failure", new TypeError("fetch failed"), "network"],
    [
      "a wrapped retry error",
      Object.assign(new Error("Failed after 3 attempts."), {
        lastError: createApiError("Too Many Requests", 429),
      }),
      "rateLimit",
    ],
    ["a string", "invalid api key", "auth"],
    ["anything else", new Error("Schema validation failed"), null],
  ])("classifies %s", (_, error, kind) => {
    expect(classifyProviderError(error)).toBe(kind);
  });
});

describe("formatProviderError", () => {
  it("names the env key for a rejected key, without echoing it", () => {
    const message = formatProviderError(
      new Error("Incorrect API key provided: sk-proj-***abcd."),
      SETTINGS,
    );
    expect(message).toContain("OPENAI_API_KEY");
    expect(message).toContain("OpenAI");
    expect(message).not.toContain("sk-proj");
  });

  it("names the model when it is not available", () => {
    expect(
      formatProviderError(createApiError("Not Found", 404), SETTINGS),
    ).toContain("gpt-5.4-mini");
  });

  it("keeps the message of an unknown error", () => {
    expect(formatProviderError(new Error("Schema mismatch"), SETTINGS)).toBe(
      "Schema mismatch",
    );
  });
});
