import { describe, expect, it } from "vitest";

import { getChatStatus } from "@/features/chat/utils/chat-status";

describe("getChatStatus", () => {
  it("is starting before the runtime has connected", () => {
    expect(getChatStatus("disconnected", false)).toBe("starting");
    expect(getChatStatus("connecting", false)).toBe("starting");
  });

  it("is online when connected and idle", () => {
    expect(getChatStatus("connected", false)).toBe("online");
  });

  it("is thinking when connected and the agent is running", () => {
    expect(getChatStatus("connected", true)).toBe("thinking");
  });

  it("is offline when the runtime connection failed, even mid-run", () => {
    expect(getChatStatus("error", false)).toBe("offline");
    expect(getChatStatus("error", true)).toBe("offline");
  });
});
