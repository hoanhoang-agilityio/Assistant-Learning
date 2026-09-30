import { describe, expect, it } from "vitest";

import { createThreadOwnerStore } from "@/features/threads/services/thread-owners";

describe("createThreadOwnerStore", () => {
  it("gives a new thread to the first user who claims it", () => {
    const store = createThreadOwnerStore();

    expect(store.claim("t1", "alice")).toBe(true);
    expect(store.claim("t1", "bob")).toBe(false);
    expect(store.getOwner("t1")).toBe("alice");
  });

  it("lets the owner claim their thread again", () => {
    const store = createThreadOwnerStore();
    store.claim("t1", "alice");

    expect(store.claim("t1", "alice")).toBe(true);
  });

  it("knows no owner for a thread nobody claimed", () => {
    expect(createThreadOwnerStore().getOwner("t1")).toBeUndefined();
  });
});
