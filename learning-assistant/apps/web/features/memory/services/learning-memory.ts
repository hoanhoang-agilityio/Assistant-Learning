import type { LearningMemory } from "@repo/agent";
import { getDatabase, getStudentMemory, saveLearnerProfile } from "@repo/db";

import { getUserRowId } from "@/services/users";

/**
 * Where the agent reads and keeps what it knows about a student across
 * conversations: the memory tables, by the Clerk id from the verified
 * session the agent was built with.
 */
export const learningMemory: LearningMemory = {
  load: async (clerkUserId) =>
    getStudentMemory(getDatabase(), await getUserRowId(clerkUserId)),
  saveProfile: async (clerkUserId, update) => {
    await saveLearnerProfile(
      getDatabase(),
      await getUserRowId(clerkUserId),
      update,
      "agent",
    );
  },
};
