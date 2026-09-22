import { describe, expect, it } from "vitest";

import {
  sealApiKey,
  unsealApiKey,
} from "@/features/api-key/services/sealed-api-key";

const SECRET = "test-secret";
const API_KEY = "sk-proj-abc123";

describe("sealApiKey / unsealApiKey", () => {
  it("round-trips the key without exposing it", () => {
    const token = sealApiKey(API_KEY, SECRET);

    expect(token).not.toContain(API_KEY);
    expect(unsealApiKey(token, SECRET)).toBe(API_KEY);
  });

  it("uses a new IV for each seal", () => {
    expect(sealApiKey(API_KEY, SECRET)).not.toBe(sealApiKey(API_KEY, SECRET));
  });

  it("rejects a token sealed with another secret", () => {
    expect(unsealApiKey(sealApiKey(API_KEY, SECRET), "other")).toBeUndefined();
  });

  it("rejects a tampered token", () => {
    const [version, iv, tag = "", ciphertext] = sealApiKey(
      API_KEY,
      SECRET,
    ).split(".");
    const flippedTag = `${tag.startsWith("A") ? "B" : "A"}${tag.slice(1)}`;
    const tampered = [version, iv, flippedTag, ciphertext].join(".");

    expect(unsealApiKey(tampered, SECRET)).toBeUndefined();
  });

  it.each([null, undefined, "", "v1.a.b", "v2.a.b.c", "garbage"])(
    "rejects %j",
    (token) => {
      expect(unsealApiKey(token, SECRET)).toBeUndefined();
    },
  );

  it("rejects everything without a secret", () => {
    expect(
      unsealApiKey(sealApiKey(API_KEY, SECRET), undefined),
    ).toBeUndefined();
  });
});
