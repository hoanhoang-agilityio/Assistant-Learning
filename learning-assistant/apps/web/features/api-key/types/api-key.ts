/** Result of checking an API key's format, or checking it with OpenAI. */
export type ApiKeyCheck = { ok: true } | { ok: false; error: string };

/** What the submit action returns: the sealed key, or why it was rejected. */
export type ApiKeySubmitResult =
  { ok: true; sealedKey: string } | { ok: false; error: string };

/** What the key form shows after a submit. */
export interface ApiKeyFormState {
  error: string | null;
}

export interface ApiKeyStore {
  /** The sealed key from `sessionStorage`, or `null` when none is saved. */
  sealedKey: string | null;
  actions: {
    setSealedKey: (sealedKey: string) => void;
    clearSealedKey: () => void;
  };
}
