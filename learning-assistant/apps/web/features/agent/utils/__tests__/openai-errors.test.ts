import { describe, expect, it } from "vitest";

import { OPENAI_MODEL } from "@/constants/openai";
import { API_KEY_ROUTE } from "@/constants/routes";
import type { OpenAIErrorKind } from "@/features/agent/types/errors";
import {
  classifyOpenAIError,
  formatOpenAIError,
} from "@/features/agent/utils/openai-errors";

const createApiError = (message: string, statusCode: number) =>
  Object.assign(new Error(message), { statusCode });

describe("classifyOpenAIError", () => {
  it.each<[string, unknown, OpenAIErrorKind | null]>([
    ["a 401", createApiError("Unauthorized", 401), "auth"],
    [
      "an OpenAI key message",
      new Error("Incorrect API key provided: sk-proj-***abcd."),
      "auth",
    ],
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
    ["a 503", createApiError("Service Unavailable", 503), "overloaded"],
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
    expect(classifyOpenAIError(error)).toBe(kind);
  });
});

describe("formatOpenAIError", () => {
  it("points to the API key page for a rejected key, without echoing it", () => {
    const message = formatOpenAIError(
      new Error("Incorrect API key provided: sk-proj-***abcd."),
    );
    expect(message).toContain(API_KEY_ROUTE);
    expect(message).toContain("OpenAI");
    expect(message).not.toContain("sk-proj");
  });

  it("names the model when it is not available", () => {
    expect(formatOpenAIError(createApiError("Not Found", 404))).toContain(
      OPENAI_MODEL,
    );
  });

  it("keeps the message of an unknown error", () => {
    expect(formatOpenAIError(new Error("Schema mismatch"))).toBe(
      "Schema mismatch",
    );
  });
});
