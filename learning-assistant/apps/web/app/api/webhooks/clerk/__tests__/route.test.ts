import { createHmac } from "node:crypto";

import { NextRequest } from "next/server";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { INVALID_WEBHOOK_STATUS } from "@/constants/webhooks";
import {
  resetTestDatabase,
  testDatabase,
} from "@/services/__tests__/database-mock";

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

const webhook = await import("@/app/api/webhooks/clerk/route");
const conversations = await import("@/app/api/conversations/route");

const SIGNING_KEY = Buffer.from("test-webhook-signing-key-32bytes!");
const SIGNING_SECRET = `whsec_${SIGNING_KEY.toString("base64")}`;

/** A webhook request signed the way Clerk (Svix) signs it. */
const signedRequest = (event: object, key = SIGNING_KEY) => {
  const body = JSON.stringify(event);
  const id = "msg_1";
  const timestamp = String(Math.floor(Date.now() / 1000));
  const signature = createHmac("sha256", key)
    .update(`${id}.${timestamp}.${body}`)
    .digest("base64");
  return new NextRequest("http://localhost/api/webhooks/clerk", {
    method: "POST",
    headers: {
      "content-type": "application/json",
      "svix-id": id,
      "svix-timestamp": timestamp,
      "svix-signature": `v1,${signature}`,
    },
    body,
  });
};

const userDeleted = (id: string) => ({
  type: "user.deleted",
  object: "event",
  data: { id, object: "user", deleted: true },
});

/** Alice's conversation with a checkpoint, as after a run. */
const seedConversation = async (): Promise<string> => {
  auth.mockResolvedValue({ isAuthenticated: true, userId: "user_alice" });
  const response = await conversations.POST(
    new Request("http://localhost/api/conversations", { method: "POST" }),
    {},
  );
  const { id } = (await response.json()) as { id: string };
  await testDatabase.checkpointer.put(
    { configurable: { thread_id: id, checkpoint_ns: "" } },
    {
      v: 4,
      id: "checkpoint-1",
      ts: new Date().toISOString(),
      channel_values: {},
      channel_versions: {},
      versions_seen: {},
    },
    { source: "input", step: -1, parents: {} },
  );
  return id;
};

const listConversationIds = async (): Promise<string[]> => {
  const response = await conversations.GET(
    new Request("http://localhost/api/conversations"),
    {},
  );
  const body = (await response.json()) as { conversations: { id: string }[] };
  return body.conversations.map(({ id }) => id);
};

beforeEach(async () => {
  vi.stubEnv("CLERK_WEBHOOK_SIGNING_SECRET", SIGNING_SECRET);
  auth.mockReset();
  await resetTestDatabase();
});

describe("Clerk webhook", () => {
  it("deletes a deleted user's conversations and their checkpoints", async () => {
    const id = await seedConversation();

    const response = await webhook.POST(
      signedRequest(userDeleted("user_alice")),
    );

    expect(response.status).toBe(200);
    expect(
      await testDatabase.checkpointer.getTuple({
        configurable: { thread_id: id },
      }),
    ).toBeUndefined();
    expect(await listConversationIds()).toEqual([]);
  });

  it("refuses a request with a bad signature and deletes nothing", async () => {
    const id = await seedConversation();

    const response = await webhook.POST(
      signedRequest(userDeleted("user_alice"), Buffer.from("wrong-key")),
    );

    expect(response.status).toBe(INVALID_WEBHOOK_STATUS);
    expect(await listConversationIds()).toEqual([id]);
  });

  it("acknowledges other events and changes nothing", async () => {
    const id = await seedConversation();

    const response = await webhook.POST(
      signedRequest({
        type: "user.updated",
        object: "event",
        data: { id: "user_alice" },
      }),
    );

    expect(response.status).toBe(200);
    expect(await listConversationIds()).toEqual([id]);
  });
});
