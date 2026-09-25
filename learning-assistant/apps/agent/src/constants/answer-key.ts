/** Version prefix of a sealed answer key, so the format can change later. */
export const SEALED_KEY_VERSION = "v1";

export const SEALED_KEY_SEPARATOR = ".";

export const SEAL_CIPHER = "aes-256-gcm";

/** AES-256 key length, in bytes. */
export const SEAL_KEY_BYTES = 32;

/** GCM's recommended IV length, in bytes. */
export const SEAL_IV_BYTES = 12;

/** HKDF `info` label: binds the derived key to this one use of the secret. */
export const SEAL_KEY_INFO = "learning-assistant/quiz-answer-key/v1";

/** Question ids are `q1`, `q2`, … in quiz order. */
export const QUESTION_ID_PREFIX = "q";

export const SEAL_ERRORS = {
  missingSecret:
    "QUIZ_SEAL_SECRET is not set, so the quiz answer key cannot be sealed. Add it to the server environment.",
  invalidToken: "The quiz answer key is invalid or was changed.",
} as const;
