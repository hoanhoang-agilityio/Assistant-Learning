import { beforeEach, describe, expect, it, vi } from "vitest";

import { UNAUTHORIZED_STATUS } from "@/constants/auth";
import { COPILOT_RUNTIME_URL } from "@/constants/copilot";

const { auth } = vi.hoisted(() => ({ auth: vi.fn() }));

vi.mock("@clerk/nextjs/server", () => ({ auth }));

const route = await import("@/app/api/copilotkit/[[...slug]]/route");

const METHODS = ["GET", "POST", "PATCH", "DELETE"] as const;

const ENDPOINTS = [
  { method: "GET", path: "/info" },
  { method: "POST", path: "/agent/learning/run" },
  { method: "POST", path: "/agent/learning/connect" },
  { method: "POST", path: "/agent/learning/stop/thread-1" },
] as const;

const requestTo = (method: string, path: string) =>
  new Request(`http://localhost${COPILOT_RUNTIME_URL}${path}`, {
    method,
    headers: { "content-type": "application/json" },
    ...(method === "GET" ? {} : { body: "{}" }),
  });

beforeEach(() => {
  auth.mockReset();
});

describe("CopilotKit runtime route without a session", () => {
  beforeEach(() => {
    auth.mockResolvedValue({ isAuthenticated: false, userId: null });
  });

  it.each(METHODS)("%s answers 401", async (method) => {
    const response = await route[method](requestTo(method, "/info"));

    expect(response.status).toBe(UNAUTHORIZED_STATUS);
  });

  it.each(ENDPOINTS)("$method $path answers 401", async ({ method, path }) => {
    const response = await route[method](requestTo(method, path));

    expect(response.status).toBe(UNAUTHORIZED_STATUS);
  });
});

describe("CopilotKit runtime route with a session", () => {
  it("reaches the runtime", async () => {
    auth.mockResolvedValue({ isAuthenticated: true, userId: "user_1" });

    const response = await route.GET(requestTo("GET", "/info"));

    expect(response.status).toBe(200);
  });
});
