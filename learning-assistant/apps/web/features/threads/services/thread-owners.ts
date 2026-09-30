import { THREAD_OWNERS_GLOBAL_KEY } from "@/features/threads/constants/threads";
import type { ThreadOwnerStore } from "@/features/threads/types/threads";

export const createThreadOwnerStore = (
  owners: Map<string, string> = new Map(),
): ThreadOwnerStore => ({
  getOwner: (threadId) => owners.get(threadId),
  claim: (threadId, userId) => {
    if (!owners.has(threadId)) {
      owners.set(threadId, userId);
    }
    return owners.get(threadId) === userId;
  },
});

const globalOwners = globalThis as typeof globalThis & {
  [THREAD_OWNERS_GLOBAL_KEY]?: Map<string, string>;
};

/**
 * Thread owners for this server process. The runtime keeps its threads in
 * process memory too, so an owner lives exactly as long as the thread it
 * guards. Kept on `globalThis` so a dev reload of this module does not
 * forget them. The `conversations` table replaces it (plan B7, M5).
 */
export const threadOwnerStore = createThreadOwnerStore(
  (globalOwners[THREAD_OWNERS_GLOBAL_KEY] ??= new Map()),
);
