import type { RuntimeRouteMethod } from "@/features/threads/types/threads";

/** Routes that start work on a thread; the caller becomes the owner of a thread nobody owns yet. */
export const THREAD_CLAIMING_ROUTES: readonly RuntimeRouteMethod[] = [
  "agent/run",
  "agent/suggest",
];

/** Routes that open a thread in the chat: its owner, or anyone for a thread that does not exist yet. */
export const THREAD_JOINING_ROUTES: readonly RuntimeRouteMethod[] = [
  "agent/connect",
];

/** Routes that read or change an existing thread: its owner only. */
export const THREAD_OWNER_ROUTES: readonly RuntimeRouteMethod[] = [
  "agent/stop",
  "threads/messages",
  "threads/events",
  "threads/state",
  "threads/archive",
  "threads/update",
];

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

export const THREAD_LIST_ROUTE: RuntimeRouteMethod = "threads/list";

/** Another user's thread is answered exactly like a thread that does not exist. */
export const THREAD_NOT_FOUND_STATUS = 404;
export const THREAD_NOT_FOUND_ERROR = "Thread not found.";

/** `globalThis` key of the process-wide owner map. */
export const THREAD_OWNERS_GLOBAL_KEY = "__learningAssistantThreadOwners";
