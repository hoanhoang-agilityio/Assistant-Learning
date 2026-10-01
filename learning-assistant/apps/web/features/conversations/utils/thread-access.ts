import { BLOCKED_THREAD_ROUTES } from "@/features/conversations/constants/threads";
import type {
  RuntimeRouteMethod,
  ThreadAccess,
} from "@/features/conversations/types/threads";

interface ThreadAccessInput {
  method: RuntimeRouteMethod;
  /** The thread the request is about; `undefined` for routes about no thread. */
  threadId: string | undefined;
  /** Whose conversation the thread is; `undefined` when it is nobody's. */
  ownerId: string | undefined;
  userId: string;
}

/**
 * Decides what a signed-in user's runtime request may do with the thread it
 * names. A thread is a conversation, created by `POST /api/conversations`:
 * only its owner may run, open, stop or read it. A thread no conversation
 * has is answered like another user's, so a made-up id gets nowhere.
 */
export const getThreadAccess = ({
  method,
  threadId,
  ownerId,
  userId,
}: ThreadAccessInput): ThreadAccess => {
  if (BLOCKED_THREAD_ROUTES.includes(method)) {
    return "deny";
  }
  if (threadId === undefined) {
    return "allow";
  }
  return ownerId === userId ? "allow" : "deny";
};
