import type { RouteInfo } from "@copilotkit/runtime/v2";

/** A CopilotKit runtime route, such as `agent/run` or `threads/messages`. */
export type RuntimeRouteMethod = RouteInfo["method"];

/**
 * What a request may do with a thread: go ahead, go ahead and become the
 * thread's owner, or be answered as if the thread did not exist.
 */
export type ThreadAccess = "allow" | "claim" | "deny";

/** Who owns each chat thread. */
export interface ThreadOwnerStore {
  getOwner: (threadId: string) => string | undefined;
  /** Makes `userId` the owner of an unowned thread. False when someone else owns it. */
  claim: (threadId: string, userId: string) => boolean;
}
