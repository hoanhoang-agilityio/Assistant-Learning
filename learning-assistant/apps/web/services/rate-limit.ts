import {
  RATE_LIMIT_PRUNE_SIZE,
  type RateLimit,
  RUN_RATE_LIMIT,
  TOO_MANY_REQUESTS_ERROR,
  TOO_MANY_REQUESTS_STATUS,
  WRITE_RATE_LIMIT,
} from "@/constants/rate-limit";

interface Window {
  count: number;
  resetAt: number;
}

/** Whether the request may go ahead, and if not, how long until it may. */
export type RateLimitResult =
  { ok: true } | { ok: false; retryAfterMs: number };

/**
 * Fixed-window counters per user, in this process's memory. Enough for one
 * server instance (plan D9); several instances would need a shared store.
 */
export const createRateLimiter = (
  { limit, windowMs }: RateLimit,
  now: () => number = Date.now,
) => {
  const windows = new Map<string, Window>();

  const prune = (time: number) => {
    for (const [key, { resetAt }] of windows) {
      if (resetAt <= time) {
        windows.delete(key);
      }
    }
  };

  return {
    take: (userId: string): RateLimitResult => {
      const time = now();
      if (windows.size > RATE_LIMIT_PRUNE_SIZE) {
        prune(time);
      }

      const current = windows.get(userId);
      if (!current || current.resetAt <= time) {
        windows.set(userId, { count: 1, resetAt: time + windowMs });
        return { ok: true };
      }
      if (current.count >= limit) {
        return { ok: false, retryAfterMs: current.resetAt - time };
      }
      current.count += 1;
      return { ok: true };
    },
  };
};

export type RateLimiter = ReturnType<typeof createRateLimiter>;

export const runRateLimiter = createRateLimiter(RUN_RATE_LIMIT);
export const writeRateLimiter = createRateLimiter(WRITE_RATE_LIMIT);

export const createTooManyRequestsResponse = (retryAfterMs: number): Response =>
  Response.json(
    { error: TOO_MANY_REQUESTS_ERROR },
    {
      status: TOO_MANY_REQUESTS_STATUS,
      headers: { "retry-after": String(Math.ceil(retryAfterMs / 1000)) },
    },
  );
