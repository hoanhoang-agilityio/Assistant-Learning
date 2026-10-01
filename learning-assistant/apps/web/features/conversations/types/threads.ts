import type { RouteInfo } from "@copilotkit/runtime/v2";

/** A CopilotKit runtime route, such as `agent/run` or `threads/messages`. */
export type RuntimeRouteMethod = RouteInfo["method"];

/** What a request may do with a thread: go ahead, or be answered as if it did not exist. */
export type ThreadAccess = "allow" | "deny";

/** Who owns each chat thread: the user whose conversation it is. */
export interface ThreadOwners {
  /** The owner's Clerk id, or `undefined` for a thread no conversation has. */
  getOwner: (threadId: string) => Promise<string | undefined>;
  /** Which of `threadIds` belong to `userId`. */
  filterOwned: (userId: string, threadIds: string[]) => Promise<Set<string>>;
}
