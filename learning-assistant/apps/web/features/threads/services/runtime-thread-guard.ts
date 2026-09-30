import {
  type AgentRunner,
  type CopilotRuntimeHooks,
  type ListThreadsResponse,
  type RouteInfo,
  supportsLocalThreadEndpoints,
} from "@copilotkit/runtime/v2";

import {
  BODY_THREAD_ID_ROUTES,
  THREAD_LIST_ROUTE,
  THREAD_NOT_FOUND_ERROR,
  THREAD_NOT_FOUND_STATUS,
} from "@/features/threads/constants/threads";
import type { ThreadOwnerStore } from "@/features/threads/types/threads";
import { getThreadAccess } from "@/features/threads/utils/thread-access";
import { createUnauthorizedResponse } from "@/services/auth";

interface ThreadGuardOptions {
  /** The signed-in user from the verified session. */
  getUserId: () => Promise<string | null>;
  owners: ThreadOwnerStore;
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

/** Whether the runtime already holds runs for `threadId`. */
const hasThreadRuns = (runner: AgentRunner, threadId: string): boolean =>
  supportsLocalThreadEndpoints(runner) &&
  runner.listThreads().some(({ id }) => id === threadId);

/**
 * Runtime hooks that keep each chat thread to the user who started it. The
 * runtime's own thread endpoints know no users: without these, any
 * signed-in user could list every thread, read its messages and events,
 * replay it through `connect`, stop it, or clear them all. Another user's
 * thread gets the same 404 as a missing one.
 */
export const createThreadGuardHooks = ({
  getUserId,
  owners,
}: ThreadGuardOptions): CopilotRuntimeHooks => ({
  onBeforeHandler: async ({ route, request, runtime }) => {
    const userId = await getUserId();
    if (!userId) {
      throw createUnauthorizedResponse();
    }

    const threadId = await getRouteThreadId(route, request);
    const ownerId =
      threadId === undefined ? undefined : owners.getOwner(threadId);
    const access = getThreadAccess({
      method: route.method,
      threadId,
      ownerId,
      userId,
      hasRuns:
        threadId !== undefined &&
        ownerId === undefined &&
        hasThreadRuns(runtime.runner, threadId),
    });
    if (access === "deny") {
      throw createThreadNotFoundResponse();
    }
    // Two users racing for one new thread: only the first claim wins.
    if (
      access === "claim" &&
      threadId !== undefined &&
      !owners.claim(threadId, userId)
    ) {
      throw createThreadNotFoundResponse();
    }
  },

  onResponse: async ({ route, response }) => {
    if (route.method !== THREAD_LIST_ROUTE || !response.ok) {
      return;
    }

    const userId = await getUserId();
    const list: ListThreadsResponse = await response.clone().json();
    const headers = new Headers(response.headers);
    headers.delete("content-length");
    return Response.json(
      {
        ...list,
        threads: list.threads.filter(
          ({ id }) => userId !== null && owners.getOwner(id) === userId,
        ),
      },
      { status: response.status, headers },
    );
  },
});
