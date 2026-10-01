import { EMPTY_STUDENT_MEMORY } from "@repo/shared/constants/memory";
import { beforeEach, describe, expect, it } from "vitest";

import type { Database } from "../client";
import {
  deleteConceptMemory,
  deleteTopicMemory,
  getStudentMemory,
  saveLearnerProfile,
} from "../repositories/memory";
import { deleteUser, ensureUser } from "../repositories/users";
import { createTestDatabase } from "../testing";

describe("memory repository", () => {
  let db: Database;
  let alice: string;
  let bob: string;

  beforeEach(async () => {
    db = await createTestDatabase();
    alice = await ensureUser(db, {
      clerkUserId: "user_alice",
      getEmail: async () => null,
    });
    bob = await ensureUser(db, {
      clerkUserId: "user_bob",
      getEmail: async () => null,
    });
  });

  it("is empty for a new student", async () => {
    expect(await getStudentMemory(db, alice)).toEqual(EMPTY_STUDENT_MEMORY);
  });

  describe("profile", () => {
    it("changes only the fields given, and forgets one set to null", async () => {
      await saveLearnerProfile(db, alice, {
        level: "advanced",
        language: "Vietnamese",
      });
      await saveLearnerProfile(db, alice, { style: "short analogies" });
      expect((await getStudentMemory(db, alice)).profile).toEqual({
        level: "advanced",
        style: "short analogies",
        language: "Vietnamese",
      });

      await saveLearnerProfile(db, alice, { language: null });
      expect((await getStudentMemory(db, alice)).profile.language).toBeNull();
    });

    it("is one student's only", async () => {
      await saveLearnerProfile(db, alice, { level: "advanced" });
      expect(await getStudentMemory(db, bob)).toEqual(EMPTY_STUDENT_MEMORY);
    });
  });

  it("deletes nothing that is not kept", async () => {
    expect(await deleteConceptMemory(db, alice, "scope")).toBe(false);
    expect(await deleteTopicMemory(db, alice, "not-a-uuid")).toBe(false);
  });

  it("goes with the user", async () => {
    await saveLearnerProfile(db, alice, { level: "advanced" });

    await deleteUser(db, "user_alice");
    expect(await getStudentMemory(db, alice)).toEqual(EMPTY_STUDENT_MEMORY);
  });
});
