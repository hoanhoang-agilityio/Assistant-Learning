import { EMPTY_STUDENT_MEMORY } from "@repo/shared/constants/memory";
import type { ProfileUpdate, StudentMemory } from "@repo/shared/schemas";

import type { LearningMemory } from "../../../types/memory";

export interface SavedProfile {
  userId: string;
  update: ProfileUpdate;
}

/**
 * Long-term memory in a map, by user id, that keeps every read and write so
 * a test can see what a run asked for and learned.
 */
export const createMemoryStore = (
  initial: Record<string, StudentMemory> = {},
) => {
  const memories = new Map(Object.entries(initial));
  const loads: string[] = [];
  const saves: SavedProfile[] = [];

  const store: LearningMemory = {
    load: async (userId) => {
      loads.push(userId);
      return memories.get(userId) ?? EMPTY_STUDENT_MEMORY;
    },
    saveProfile: async (userId, update) => {
      saves.push({ userId, update });
      const memory = memories.get(userId) ?? EMPTY_STUDENT_MEMORY;
      memories.set(userId, {
        ...memory,
        profile: { ...memory.profile, ...update },
      });
    },
  };
  return { store, memories, loads, saves };
};
