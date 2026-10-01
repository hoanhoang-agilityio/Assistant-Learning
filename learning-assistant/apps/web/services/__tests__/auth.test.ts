import { beforeEach, describe, expect, it, vi } from "vitest";

import { UNAUTHORIZED_ERROR, UNAUTHORIZED_STATUS } from "@/constants/auth";
import {
  getSignedInUserId,
  requireSignedInUser,
  withSignedInUser,
} from "@/services/auth";

const { auth, redirectToSignIn } = vi.hoisted(() => ({
  auth: vi.fn(),
  redirectToSignIn: vi.fn(() => {
    throw new Error("NEXT_REDIRECT");
  }),
}));

vi.mock("@clerk/nextjs/server", () => ({ auth }));

const signIn = (userId: string) =>
  auth.mockResolvedValue({ isAuthenticated: true, userId, redirectToSignIn });

const signOut = () =>
  auth.mockResolvedValue({
    isAuthenticated: false,
    userId: null,
    redirectToSignIn,
  });

beforeEach(() => {
  vi.clearAllMocks();
});

describe("getSignedInUserId", () => {
  it("returns the session's user id", async () => {
    signIn("user_1");

    expect(await getSignedInUserId()).toBe("user_1");
  });

  it("returns null when signed out", async () => {
    signOut();

    expect(await getSignedInUserId()).toBeNull();
  });
});

describe("requireSignedInUser", () => {
  it("returns the user id when signed in", async () => {
    signIn("user_1");

    expect(await requireSignedInUser()).toBe("user_1");
    expect(redirectToSignIn).not.toHaveBeenCalled();
  });

  it("redirects to sign-in when signed out", async () => {
    signOut();

    await expect(requireSignedInUser()).rejects.toThrow("NEXT_REDIRECT");
    expect(redirectToSignIn).toHaveBeenCalledOnce();
  });
});

describe("withSignedInUser", () => {
  const handler = vi.fn(async (_request: Request, userId: string) =>
    Response.json({ userId }),
  );
  const request = new Request("http://localhost/api/anything", {
    // A client-sent id must never be used.
    headers: { "x-user-id": "user_forged" },
  });

  it("answers 401 and never runs the handler when signed out", async () => {
    signOut();

    const response = await withSignedInUser(handler)(request, {});

    expect(response.status).toBe(UNAUTHORIZED_STATUS);
    expect(await response.json()).toEqual({ error: UNAUTHORIZED_ERROR });
    expect(handler).not.toHaveBeenCalled();
  });

  it("runs the handler with the session's user id, not the client's", async () => {
    signIn("user_1");

    const response = await withSignedInUser(handler)(request, {});

    expect(await response.json()).toEqual({ userId: "user_1" });
  });

  it("passes the route's context on", async () => {
    signIn("user_1");
    const context = { params: Promise.resolve({ id: "c1" }) };

    await withSignedInUser(handler)(request, context);

    expect(handler).toHaveBeenCalledWith(request, "user_1", context);
  });
});
