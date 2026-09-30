import { beforeEach, describe, expect, it, vi } from "vitest";

import {
  API_KEY_ERRORS,
  API_KEY_FIELD,
} from "@/features/api-key/constants/api-key";
import { submitApiKey } from "@/features/api-key/services/api-key-actions";
import { validateApiKey } from "@/features/api-key/services/validate-api-key";

const { auth } = vi.hoisted(() => ({ auth: vi.fn() }));

vi.mock("@clerk/nextjs/server", () => ({ auth }));
vi.mock("@/features/api-key/services/validate-api-key", () => ({
  validateApiKey: vi.fn(async () => ({ ok: true })),
}));

const form = (apiKey: string) => {
  const data = new FormData();
  data.set(API_KEY_FIELD, apiKey);
  return data;
};

beforeEach(() => {
  vi.clearAllMocks();
  vi.stubEnv("API_KEY_SEAL_SECRET", "test-secret");
});

describe("submitApiKey", () => {
  it("refuses a signed-out caller without checking the key", async () => {
    auth.mockResolvedValue({ isAuthenticated: false, userId: null });

    const result = await submitApiKey(form("sk-proj-abc123"));

    expect(result).toEqual({ ok: false, error: API_KEY_ERRORS.signedOut });
    expect(validateApiKey).not.toHaveBeenCalled();
  });

  it("seals the key for a signed-in user", async () => {
    auth.mockResolvedValue({ isAuthenticated: true, userId: "user_1" });

    const result = await submitApiKey(form("sk-proj-abc123"));

    expect(result.ok).toBe(true);
  });
});
