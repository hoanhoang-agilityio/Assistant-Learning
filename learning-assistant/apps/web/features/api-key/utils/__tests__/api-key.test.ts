import { describe, expect, it } from "vitest";

import { API_KEY_ERRORS } from "@/features/api-key/constants/api-key";
import {
  checkApiKeyFormat,
  describeApiKeyStatus,
  normalizeApiKey,
} from "@/features/api-key/utils/api-key";

describe("normalizeApiKey", () => {
  it("trims a string", () => {
    expect(normalizeApiKey("  sk-abc \n")).toBe("sk-abc");
  });

  it("returns an empty string for anything else", () => {
    expect(normalizeApiKey(null)).toBe("");
    expect(normalizeApiKey(new Blob())).toBe("");
  });
});

describe("checkApiKeyFormat", () => {
  it("accepts OpenAI key shapes", () => {
    expect(checkApiKeyFormat("sk-abc123")).toEqual({ ok: true });
    expect(checkApiKeyFormat("sk-proj-abc_123")).toEqual({ ok: true });
  });

  it("rejects an empty key", () => {
    expect(checkApiKeyFormat("")).toEqual({
      ok: false,
      error: API_KEY_ERRORS.empty,
    });
  });

  it.each(["abc123", "sk- abc", "pk-abc"])("rejects %j", (apiKey) => {
    expect(checkApiKeyFormat(apiKey)).toEqual({
      ok: false,
      error: API_KEY_ERRORS.format,
    });
  });
});

describe("describeApiKeyStatus", () => {
  it.each([
    [200, { ok: true }],
    [401, { ok: false, error: API_KEY_ERRORS.invalid }],
    [403, { ok: false, error: API_KEY_ERRORS.forbidden }],
    [429, { ok: false, error: API_KEY_ERRORS.rateLimit }],
    [500, { ok: false, error: API_KEY_ERRORS.unexpected }],
  ])("maps %i", (status, expected) => {
    expect(describeApiKeyStatus(status)).toEqual(expected);
  });
});
