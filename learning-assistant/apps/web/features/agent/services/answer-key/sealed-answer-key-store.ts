import {
  createCipheriv,
  createDecipheriv,
  hkdfSync,
  randomBytes,
} from "node:crypto";

import { type AnswerKey, AnswerKeySchema } from "@repo/shared/schemas";

import {
  SEAL_CIPHER,
  SEAL_ERRORS,
  SEAL_IV_BYTES,
  SEAL_KEY_BYTES,
  SEAL_KEY_INFO,
  SEALED_KEY_SEPARATOR,
  SEALED_KEY_VERSION,
} from "@/features/agent/constants/answer-key";
import type { AnswerKeyStore } from "@/features/agent/types/answer-key";

const ENCODING = "base64url";

const deriveKey = (secret: string): Buffer =>
  Buffer.from(hkdfSync("sha256", secret, "", SEAL_KEY_INFO, SEAL_KEY_BYTES));

/**
 * Seals the answer key into state with AES-256-GCM: a random IV per quiz, and
 * the quiz id as additional authenticated data, so a key cannot be moved to
 * another quiz. The token is `v1.<iv>.<tag>.<ciphertext>` (base64url). A
 * missing secret fails when the store is used, not when it is created, so the
 * rest of the app keeps working and the quiz tool explains the problem.
 */
export class SealedAnswerKeyStore implements AnswerKeyStore {
  private readonly key: Buffer | null;

  constructor(secret: string | undefined) {
    this.key = secret ? deriveKey(secret) : null;
  }

  private requireKey(): Buffer {
    if (!this.key) throw new Error(SEAL_ERRORS.missingSecret);
    return this.key;
  }

  seal = async (quizId: string, answerKey: AnswerKey): Promise<string> => {
    const key = this.requireKey();
    const iv = randomBytes(SEAL_IV_BYTES);

    const cipher = createCipheriv(SEAL_CIPHER, key, iv);
    cipher.setAAD(Buffer.from(quizId));
    const ciphertext = Buffer.concat([
      cipher.update(JSON.stringify(answerKey), "utf8"),
      cipher.final(),
    ]);

    return [SEALED_KEY_VERSION, iv, cipher.getAuthTag(), ciphertext]
      .map((part) =>
        typeof part === "string" ? part : part.toString(ENCODING),
      )
      .join(SEALED_KEY_SEPARATOR);
  };

  unseal = async (quizId: string, token: string): Promise<AnswerKey> => {
    const key = this.requireKey();
    const [version, iv, tag, ciphertext, ...rest] =
      token.split(SEALED_KEY_SEPARATOR);
    if (
      version !== SEALED_KEY_VERSION ||
      !iv ||
      !tag ||
      !ciphertext ||
      rest.length > 0
    ) {
      throw new Error(SEAL_ERRORS.invalidToken);
    }

    try {
      const decipher = createDecipheriv(
        SEAL_CIPHER,
        key,
        Buffer.from(iv, ENCODING),
      );
      decipher.setAAD(Buffer.from(quizId));
      decipher.setAuthTag(Buffer.from(tag, ENCODING));
      const plaintext = Buffer.concat([
        decipher.update(Buffer.from(ciphertext, ENCODING)),
        decipher.final(),
      ]).toString("utf8");
      return AnswerKeySchema.parse(JSON.parse(plaintext));
    } catch {
      throw new Error(SEAL_ERRORS.invalidToken);
    }
  };
}
