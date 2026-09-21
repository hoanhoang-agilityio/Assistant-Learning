import type { AnswerKey } from "@repo/shared/schemas";
import { describe, expect, it } from "vitest";

import { SEAL_ERRORS } from "@/features/agent/constants/answer-key";
import { SealedAnswerKeyStore } from "@/features/agent/services/answer-key/sealed-answer-key-store";

const SECRET = "test-secret-for-sealing";
const QUIZ_ID = "quiz-1";
const KEY: AnswerKey = {
  correctIndex: [2, 0, 3],
  explanations: ["Because A.", "Because B.", "Because C."],
};

/** Flips one character of the token part at `index`. */
const tamper = (token: string, index: number) => {
  const parts = token.split(".");
  const part = parts[index] ?? "";
  const flipped = part[0] === "A" ? "B" : "A";
  parts[index] = `${flipped}${part.slice(1)}`;
  return parts.join(".");
};

describe("SealedAnswerKeyStore", () => {
  const store = new SealedAnswerKeyStore(SECRET);

  it("round-trips an answer key", async () => {
    const token = await store.seal(QUIZ_ID, KEY);
    await expect(store.unseal(QUIZ_ID, token)).resolves.toEqual(KEY);
  });

  it("does not leak the key in the token", async () => {
    const token = await store.seal(QUIZ_ID, KEY);
    expect(token).not.toContain("correctIndex");
    expect(token).not.toContain("Because");
    expect(token.startsWith("v1.")).toBe(true);
  });

  it("uses a fresh IV for every seal", async () => {
    const first = await store.seal(QUIZ_ID, KEY);
    const second = await store.seal(QUIZ_ID, KEY);
    expect(first).not.toBe(second);
  });

  it.each([
    ["IV", 1],
    ["auth tag", 2],
    ["ciphertext", 3],
  ])("rejects a token with a changed %s", async (_, index) => {
    const token = await store.seal(QUIZ_ID, KEY);
    await expect(store.unseal(QUIZ_ID, tamper(token, index))).rejects.toThrow(
      SEAL_ERRORS.invalidToken,
    );
  });

  it("rejects a key moved to another quiz", async () => {
    const token = await store.seal(QUIZ_ID, KEY);
    await expect(store.unseal("quiz-2", token)).rejects.toThrow(
      SEAL_ERRORS.invalidToken,
    );
  });

  it("rejects a key sealed with another secret", async () => {
    const token = await new SealedAnswerKeyStore("other").seal(QUIZ_ID, KEY);
    await expect(store.unseal(QUIZ_ID, token)).rejects.toThrow(
      SEAL_ERRORS.invalidToken,
    );
  });

  it.each(["", "v1.a.b", "v2.a.b.c", "v1.a.b.c.d"])(
    "rejects a malformed token %j",
    async (token) => {
      await expect(store.unseal(QUIZ_ID, token)).rejects.toThrow(
        SEAL_ERRORS.invalidToken,
      );
    },
  );

  it("fails on use when the secret is missing", async () => {
    const missing = new SealedAnswerKeyStore(undefined);
    await expect(missing.seal(QUIZ_ID, KEY)).rejects.toThrow(
      SEAL_ERRORS.missingSecret,
    );
  });
});
