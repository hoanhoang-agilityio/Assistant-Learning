import type { RuntimeRouteMethod } from "@/features/conversations/types/threads";

/** Routes that act on every user's threads at once. Never allowed. */
export const BLOCKED_THREAD_ROUTES: readonly RuntimeRouteMethod[] = [
  "threads/clear",
  "threads/subscribe",
];

/** Routes whose thread id is in the JSON body, not the path. */
export const BODY_THREAD_ID_ROUTES: readonly RuntimeRouteMethod[] = [
  "agent/run",
  "agent/suggest",
  "agent/connect",
];

/** Routes that start an agent run, and so count toward the run rate limit. */
export const RUN_ROUTES: readonly RuntimeRouteMethod[] = [
  "agent/run",
  "agent/suggest",
];

export const THREAD_LIST_ROUTE: RuntimeRouteMethod = "threads/list";

/** Another user's thread is answered exactly like a thread that does not exist. */
export const THREAD_NOT_FOUND_STATUS = 404;
export const THREAD_NOT_FOUND_ERROR = "Thread not found.";
