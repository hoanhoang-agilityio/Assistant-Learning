import { auth } from "@clerk/nextjs/server";

import { UNAUTHORIZED_ERROR, UNAUTHORIZED_STATUS } from "@/constants/auth";

/**
 * The signed-in user's Clerk id, from the session Clerk verified on the
 * server, or `null`. The only source of a user id: never a request body,
 * query or header the client sent.
 */
export const getSignedInUserId = async (): Promise<string | null> => {
  const { isAuthenticated, userId } = await auth();
  return isAuthenticated ? userId : null;
};

/** For pages: the signed-in user's id; a signed-out visitor is sent to sign in. */
export const requireSignedInUser = async (): Promise<string> => {
  const { isAuthenticated, userId, redirectToSignIn } = await auth();
  if (!isAuthenticated) {
    return redirectToSignIn();
  }
  return userId;
};

export const createUnauthorizedResponse = (): Response =>
  Response.json({ error: UNAUTHORIZED_ERROR }, { status: UNAUTHORIZED_STATUS });

/**
 * For route handlers: runs `handler` only for a signed-in user and answers
 * 401 otherwise. `proxy.ts` makes the session readable but checks nothing,
 * so every handler goes through this. `context` is the route's own (its
 * `params`), passed on as it is.
 */
export const withSignedInUser =
  <Context = unknown>(
    handler: (
      request: Request,
      userId: string,
      context: Context,
    ) => Promise<Response>,
  ) =>
  async (request: Request, context: Context): Promise<Response> => {
    const userId = await getSignedInUserId();
    if (!userId) {
      return createUnauthorizedResponse();
    }
    return handler(request, userId, context);
  };
