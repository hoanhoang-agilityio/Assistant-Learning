import { describe, expect, it } from "vitest";

import { TOO_MANY_REQUESTS_STATUS } from "@/constants/rate-limit";
import {
  createRateLimiter,
  createTooManyRequestsResponse,
} from "@/services/rate-limit";

describe("createRateLimiter", () => {
  it("lets a user make `limit` requests per window, then refuses", () => {
    let time = 0;
    const limiter = createRateLimiter({ limit: 2, windowMs: 1000 }, () => time);

    expect(limiter.take("alice")).toEqual({ ok: true });
    expect(limiter.take("alice")).toEqual({ ok: true });
    time = 400;
    expect(limiter.take("alice")).toEqual({ ok: false, retryAfterMs: 600 });
  });

  it("counts each user on their own", () => {
    const limiter = createRateLimiter({ limit: 1, windowMs: 1000 }, () => 0);

    expect(limiter.take("alice").ok).toBe(true);
    expect(limiter.take("bob").ok).toBe(true);
    expect(limiter.take("alice").ok).toBe(false);
  });

  it("starts over when the window ends", () => {
    let time = 0;
    const limiter = createRateLimiter({ limit: 1, windowMs: 1000 }, () => time);

    limiter.take("alice");
    time = 1000;
    expect(limiter.take("alice").ok).toBe(true);
  });
});

describe("createTooManyRequestsResponse", () => {
  it("answers 429 with the seconds to wait", () => {
    const response = createTooManyRequestsResponse(1500);

    expect(response.status).toBe(TOO_MANY_REQUESTS_STATUS);
    expect(response.headers.get("retry-after")).toBe("2");
  });
});
