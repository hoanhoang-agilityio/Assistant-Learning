import type {
  CopilotRuntimeHooks,
  ListThreadsResponse,
  RouteInfo,
} from "@copilotkit/runtime/v2";

import {
  BODY_THREAD_ID_ROUTES,
  RUN_ROUTES,
  THREAD_LIST_ROUTE,
  THREAD_NOT_FOUND_ERROR,
  THREAD_NOT_FOUND_STATUS,
} from "@/features/conversations/constants/threads";
import type { ThreadOwners } from "@/features/conversations/types/threads";
import { getThreadAccess } from "@/features/conversations/utils/thread-access";
import { createUnauthorizedResponse } from "@/services/auth";
import {
  createTooManyRequestsResponse,
  type RateLimiter,
} from "@/services/rate-limit";

interface ThreadGuardOptions {
  /** The signed-in user from the verified session. */
  getUserId: () => Promise<string | null>;
  owners: ThreadOwners;
  /** Caps how many runs a user starts. */
  runLimiter: RateLimiter;
}

const createThreadNotFoundResponse = (): Response =>
  Response.json(
    { error: THREAD_NOT_FOUND_ERROR },
    { status: THREAD_NOT_FOUND_STATUS },
  );

const readBodyThreadId = async (
  request: Request,
): Promise<string | undefined> => {
  try {
    const body: unknown = await request.clone().json();
    const threadId = (body as { threadId?: unknown } | null)?.threadId;
    return typeof threadId === "string" ? threadId : undefined;
  } catch {
    return undefined;
  }
};

const getRouteThreadId = async (
  route: RouteInfo,
  request: Request,
): Promise<string | undefined> => {
  if ("threadId" in route) {
    return route.threadId;
  }
  return BODY_THREAD_ID_ROUTES.includes(route.method)
    ? readBodyThreadId(request)
    : undefined;
};

/**
 * Runtime hooks that keep each chat thread to the user whose conversation
 * it is. The runtime's own thread endpoints know no users: without these,
 * any signed-in user could run, replay, stop or read any thread, list
 * every thread, or clear them all. Another user's thread, and a thread no
 * conversation has, get the same 404. Runs also count toward the user's
 * rate limit.
 */
export const createThreadGuardHooks = ({
  getUserId,
  owners,
  runLimiter,
}: ThreadGuardOptions): CopilotRuntimeHooks => ({
  onBeforeHandler: async ({ route, request }) => {
    const userId = await getUserId();
    if (!userId) {
      throw createUnauthorizedResponse();
    }

    const threadId = await getRouteThreadId(route, request);
    const ownerId =
      threadId === undefined ? undefined : await owners.getOwner(threadId);
    const access = getThreadAccess({
      method: route.method,
      threadId,
      ownerId,
      userId,
    });
    if (access === "deny") {
      throw createThreadNotFoundResponse();
    }

    if (RUN_ROUTES.includes(route.method)) {
      const limit = runLimiter.take(userId);
      if (!limit.ok) {
        throw createTooManyRequestsResponse(limit.retryAfterMs);
      }
    }
  },

  onResponse: async ({ route, response }) => {
    if (route.method !== THREAD_LIST_ROUTE || !response.ok) {
      return;
    }

    const userId = await getUserId();
    const list: ListThreadsResponse = await response.clone().json();
    const owned =
      userId === null
        ? new Set<string>()
        : await owners.filterOwned(
            userId,
            list.threads.map(({ id }) => id),
          );
    const headers = new Headers(response.headers);
    headers.delete("content-length");
    return Response.json(
      { ...list, threads: list.threads.filter(({ id }) => owned.has(id)) },
      { status: response.status, headers },
    );
  },
});
