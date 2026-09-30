import {
  BLOCKED_THREAD_ROUTES,
  THREAD_CLAIMING_ROUTES,
  THREAD_JOINING_ROUTES,
  THREAD_OWNER_ROUTES,
} from "@/features/threads/constants/threads";
import type {
  RuntimeRouteMethod,
  ThreadAccess,
} from "@/features/threads/types/threads";

interface ThreadAccessInput {
  method: RuntimeRouteMethod;
  /** The thread the request is about; `undefined` for routes about no thread. */
  threadId: string | undefined;
  ownerId: string | undefined;
  userId: string;
  /**
   * The runtime already holds runs for this thread. An unowned thread with
   * runs was started before owners were kept (a deploy into a running
   * process), so it belongs to nobody who may see it.
   */
  hasRuns: boolean;
}

/** Decides what a signed-in user's runtime request may do with the thread it names. */
export const getThreadAccess = ({
  method,
  threadId,
  ownerId,
  userId,
  hasRuns,
}: ThreadAccessInput): ThreadAccess => {
  if (BLOCKED_THREAD_ROUTES.includes(method)) {
    return "deny";
  }
  if (threadId === undefined) {
    return "allow";
  }

  const isUnowned = ownerId === undefined;
  if (isUnowned && hasRuns) {
    return "deny";
  }

  const isOwner = ownerId === userId;
  if (THREAD_CLAIMING_ROUTES.includes(method)) {
    if (isUnowned) {
      return "claim";
    }
    return isOwner ? "allow" : "deny";
  }
  if (THREAD_JOINING_ROUTES.includes(method)) {
    return isOwner || isUnowned ? "allow" : "deny";
  }
  if (THREAD_OWNER_ROUTES.includes(method)) {
    return isOwner ? "allow" : "deny";
  }
  return "allow";
};
