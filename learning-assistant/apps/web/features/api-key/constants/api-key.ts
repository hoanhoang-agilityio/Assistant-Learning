import type { ApiKeyFormState } from "@/features/api-key/types/api-key";

/**
 * `sessionStorage` key for the sealed (encrypted) OpenAI API key. Only the
 * server can open it; the plain key is never stored in the browser.
 */
export const API_KEY_STORAGE_KEY = "learning-assistant:openai-key";

/** Request header that carries the sealed key to the CopilotKit runtime. */
export const API_KEY_HEADER = "x-openai-key-sealed";

/** Server env variable holding the secret used to seal the key. */
export const API_KEY_SEAL_SECRET_ENV_KEY = "API_KEY_SEAL_SECRET";

/** Version prefix of a sealed key, so the format can change later. */
export const SEALED_API_KEY_VERSION = "v1";

export const SEALED_API_KEY_SEPARATOR = ".";

export const API_KEY_SEAL_CIPHER = "aes-256-gcm";

/** AES-256 key length, in bytes. */
export const API_KEY_SEAL_KEY_BYTES = 32;

/** GCM's recommended IV length, in bytes. */
export const API_KEY_SEAL_IV_BYTES = 12;

/** HKDF `info` label: binds the derived key to this one use of the secret. */
export const API_KEY_SEAL_INFO = "learning-assistant/openai-api-key/v1";

/** Form field name of the key input. */
export const API_KEY_FIELD = "apiKey";

/** Every OpenAI secret key starts with this (`sk-…`, `sk-proj-…`). */
export const API_KEY_PREFIX = "sk-";

/** A free authenticated call used to check that OpenAI accepts the key. */
export const OPENAI_MODELS_URL = "https://api.openai.com/v1/models";

export const API_KEY_CHECK_TIMEOUT_MS = 10_000;

/** Where the user creates a key, linked from the form. */
export const OPENAI_KEYS_URL = "https://platform.openai.com/api-keys";

export const API_KEY_ERRORS = {
  empty: "Enter your OpenAI API key.",
  format: `That does not look like an OpenAI API key. It should start with "${API_KEY_PREFIX}".`,
  invalid:
    "OpenAI rejected this key. Check that it is correct and not revoked.",
  forbidden:
    "This key has no permission to use the OpenAI API. Check its project and permissions.",
  rateLimit:
    "OpenAI is rate-limiting this key or its quota is used up. Check your billing, then try again.",
  unreachable:
    "Could not reach OpenAI to check the key. Try again in a moment.",
  unexpected:
    "OpenAI could not check the key right now. Try again in a moment.",
  missingSecret:
    "API key storage is currently unavailable. Please contact the administrator.",
} as const;

export const INITIAL_API_KEY_FORM_STATE: ApiKeyFormState = { error: null };
