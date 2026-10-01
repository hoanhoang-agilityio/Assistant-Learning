import { beforeEach, describe, expect, it, vi } from "vitest";

import { UNAUTHORIZED_STATUS } from "@/constants/auth";
import { INVALID_SETTINGS_STATUS } from "@/features/settings/constants/settings";
import { resetTestDatabase } from "@/services/__tests__/database-mock";

const { auth, currentUser } = vi.hoisted(() => ({
  auth: vi.fn(),
  currentUser: vi.fn(async () => null),
}));

vi.mock("@clerk/nextjs/server", () => ({ auth, currentUser }));
vi.mock("@repo/db/client", () =>
  import("@/services/__tests__/database-mock").then((m) => m.CLIENT_MOCK),
);
vi.mock("@repo/db/checkpointer", () =>
  import("@/services/__tests__/database-mock").then((m) => m.CHECKPOINTER_MOCK),
);

const route = await import("@/app/api/settings/route");

const URL = "http://localhost/api/settings";
const SETTINGS = { questionCount: 8, learningLevel: "advanced", theme: "dark" };

const signInAs = (userId: string) =>
  auth.mockResolvedValue({ isAuthenticated: true, userId });

const read = async () => (await route.GET(new Request(URL), {})).json();

const save = (body: unknown) =>
  route.PUT(
    new Request(URL, { method: "PUT", body: JSON.stringify(body) }),
    {},
  );

beforeEach(async () => {
  auth.mockReset();
  await resetTestDatabase();
  signInAs("alice");
});

describe("/api/settings", () => {
  it("has no settings before the first save", async () => {
    expect(await read()).toEqual({ settings: null });
  });

  it("saves the settings for the user only", async () => {
    expect((await save(SETTINGS)).status).toBe(200);
    expect(await read()).toEqual({ settings: SETTINGS });

    signInAs("bob");
    expect(await read()).toEqual({ settings: null });
  });

  it("refuses settings out of range", async () => {
    const response = await save({ ...SETTINGS, questionCount: 99 });

    expect(response.status).toBe(INVALID_SETTINGS_STATUS);
  });

  it("answers 401 without a session", async () => {
    auth.mockResolvedValue({ isAuthenticated: false, userId: null });

    expect((await save(SETTINGS)).status).toBe(UNAUTHORIZED_STATUS);
  });
});
