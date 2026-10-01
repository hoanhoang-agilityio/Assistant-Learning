/** How many requests of one kind a user may make per window. */
export interface RateLimit {
  limit: number;
  windowMs: number;
}

/** Agent runs: each one is several model calls on the user's key. */
export const RUN_RATE_LIMIT: RateLimit = { limit: 20, windowMs: 60_000 };

/** Conversation and settings changes. */
export const WRITE_RATE_LIMIT: RateLimit = { limit: 60, windowMs: 60_000 };

/** Above this many tracked users, finished windows are dropped. */
export const RATE_LIMIT_PRUNE_SIZE = 1000;

export const TOO_MANY_REQUESTS_STATUS = 429;
export const TOO_MANY_REQUESTS_ERROR =
  "Too many requests. Wait a moment and try again.";
