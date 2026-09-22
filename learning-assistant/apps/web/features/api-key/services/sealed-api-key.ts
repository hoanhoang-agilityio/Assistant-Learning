import {
  createCipheriv,
  createDecipheriv,
  hkdfSync,
  randomBytes,
} from "node:crypto";

import {
  API_KEY_SEAL_CIPHER,
  API_KEY_SEAL_INFO,
  API_KEY_SEAL_IV_BYTES,
  API_KEY_SEAL_KEY_BYTES,
  SEALED_API_KEY_SEPARATOR,
  SEALED_API_KEY_VERSION,
} from "@/features/api-key/constants/api-key";

const ENCODING = "base64url";

const deriveKey = (secret: string): Buffer =>
  Buffer.from(
    hkdfSync("sha256", secret, "", API_KEY_SEAL_INFO, API_KEY_SEAL_KEY_BYTES),
  );

/**
 * Seals the user's API key with AES-256-GCM so the browser can keep it without
 * holding the plain key. The token is `v1.<iv>.<tag>.<ciphertext>`
 * (base64url), with a random IV per seal.
 */
export const sealApiKey = (apiKey: string, secret: string): string => {
  const iv = randomBytes(API_KEY_SEAL_IV_BYTES);
  const cipher = createCipheriv(API_KEY_SEAL_CIPHER, deriveKey(secret), iv);
  const ciphertext = Buffer.concat([
    cipher.update(apiKey, "utf8"),
    cipher.final(),
  ]);

  return [SEALED_API_KEY_VERSION, iv, cipher.getAuthTag(), ciphertext]
    .map((part) => (typeof part === "string" ? part : part.toString(ENCODING)))
    .join(SEALED_API_KEY_SEPARATOR);
};

/**
 * Opens a sealed key. Returns `undefined` for a missing, malformed or
 * tampered token, or one sealed with another secret.
 */
export const unsealApiKey = (
  token: string | null | undefined,
  secret: string | undefined,
): string | undefined => {
  if (!token || !secret) {
    return undefined;
  }
  const [version, iv, tag, ciphertext, ...rest] = token.split(
    SEALED_API_KEY_SEPARATOR,
  );
  if (
    version !== SEALED_API_KEY_VERSION ||
    !iv ||
    !tag ||
    !ciphertext ||
    rest.length > 0
  ) {
    return undefined;
  }

  try {
    const decipher = createDecipheriv(
      API_KEY_SEAL_CIPHER,
      deriveKey(secret),
      Buffer.from(iv, ENCODING),
    );
    decipher.setAuthTag(Buffer.from(tag, ENCODING));
    return Buffer.concat([
      decipher.update(Buffer.from(ciphertext, ENCODING)),
      decipher.final(),
    ]).toString("utf8");
  } catch {
    return undefined;
  }
};
