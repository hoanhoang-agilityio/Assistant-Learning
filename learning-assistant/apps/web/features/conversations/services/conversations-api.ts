import {
  createConversation,
  deleteConversation,
  getConversation,
  getDatabase,
  getDraftAnswers,
  getThreadCheckpointer,
  listConversations,
  listQuizAttempts,
  renameConversation,
  saveDraftAnswers,
} from "@repo/db";
import {
  DraftAnswersSchema,
  RenameConversationSchema,
} from "@repo/shared/schemas";

import {
  BAD_REQUEST_STATUS,
  CONVERSATION_NOT_FOUND_ERROR,
  CONVERSATION_NOT_FOUND_STATUS,
  CREATED_STATUS,
  INVALID_ANSWERS_ERROR,
  INVALID_TITLE_ERROR,
  NO_CONTENT_STATUS,
} from "@/features/conversations/constants/conversations";
import {
  createTooManyRequestsResponse,
  writeRateLimiter,
} from "@/services/rate-limit";
import { getUserRowId } from "@/services/users";

/** A route under `/api/conversations/[id]`. */
export interface ConversationRouteContext {
  params: Promise<{ id: string }>;
}

const createNotFoundResponse = (): Response =>
  Response.json(
    { error: CONVERSATION_NOT_FOUND_ERROR },
    { status: CONVERSATION_NOT_FOUND_STATUS },
  );

/** A 429 when the user has changed too much too fast, otherwise `null`. */
const limitWrites = (clerkUserId: string): Response | null => {
  const limit = writeRateLimiter.take(clerkUserId);
  return limit.ok ? null : createTooManyRequestsResponse(limit.retryAfterMs);
};

const readJson = async (request: Request): Promise<unknown> => {
  try {
    return await request.json();
  } catch {
    return null;
  }
};

/** `GET /api/conversations`: the user's conversations, most recent first. */
export const listConversationsHandler = async (
  _request: Request,
  clerkUserId: string,
): Promise<Response> => {
  const userId = await getUserRowId(clerkUserId);
  return Response.json({
    conversations: await listConversations(getDatabase(), userId),
  });
};

/** `POST /api/conversations`: a conversation for a new topic (D5). */
export const createConversationHandler = async (
  _request: Request,
  clerkUserId: string,
): Promise<Response> => {
  const limited = limitWrites(clerkUserId);
  if (limited) {
    return limited;
  }

  const userId = await getUserRowId(clerkUserId);
  return Response.json(await createConversation(getDatabase(), userId), {
    status: CREATED_STATUS,
  });
};

/** `GET /api/conversations/[id]`. */
export const getConversationHandler = async (
  _request: Request,
  clerkUserId: string,
  { params }: ConversationRouteContext,
): Promise<Response> => {
  const { id } = await params;
  const userId = await getUserRowId(clerkUserId);
  const conversation = await getConversation(getDatabase(), userId, id);
  return conversation ? Response.json(conversation) : createNotFoundResponse();
};

/** `PATCH /api/conversations/[id]` with `{ title }`: the student's own name for it. */
export const renameConversationHandler = async (
  request: Request,
  clerkUserId: string,
  { params }: ConversationRouteContext,
): Promise<Response> => {
  const limited = limitWrites(clerkUserId);
  if (limited) {
    return limited;
  }

  const parsed = RenameConversationSchema.safeParse(await readJson(request));
  if (!parsed.success) {
    return Response.json(
      { error: INVALID_TITLE_ERROR },
      { status: BAD_REQUEST_STATUS },
    );
  }

  const { id } = await params;
  const userId = await getUserRowId(clerkUserId);
  const renamed = await renameConversation(
    getDatabase(),
    userId,
    id,
    parsed.data.title,
  );
  return renamed ? Response.json(renamed) : createNotFoundResponse();
};

/**
 * `DELETE /api/conversations/[id]`: for good. The thread's checkpoints go
 * first, then the conversation's rows, which cascade to its research,
 * material and attempts.
 */
export const deleteConversationHandler = async (
  _request: Request,
  clerkUserId: string,
  { params }: ConversationRouteContext,
): Promise<Response> => {
  const limited = limitWrites(clerkUserId);
  if (limited) {
    return limited;
  }

  const { id } = await params;
  const userId = await getUserRowId(clerkUserId);
  const db = getDatabase();
  if (!(await getConversation(db, userId, id))) {
    return createNotFoundResponse();
  }

  await getThreadCheckpointer().deleteThread(id);
  await deleteConversation(db, userId, id);
  return new Response(null, { status: NO_CONTENT_STATUS });
};

/** `GET /api/conversations/[id]/attempts`: its quiz attempts, without answer keys. */
export const listAttemptsHandler = async (
  _request: Request,
  clerkUserId: string,
  { params }: ConversationRouteContext,
): Promise<Response> => {
  const { id } = await params;
  const userId = await getUserRowId(clerkUserId);
  const db = getDatabase();
  if (!(await getConversation(db, userId, id))) {
    return createNotFoundResponse();
  }
  return Response.json({ attempts: await listQuizAttempts(db, id) });
};

/**
 * `GET /api/conversations/[id]/answers`: the answers picked so far for its
 * quiz (`{ draft: null }` when nothing is open), to put back after a reload.
 */
export const getDraftAnswersHandler = async (
  _request: Request,
  clerkUserId: string,
  { params }: ConversationRouteContext,
): Promise<Response> => {
  const { id } = await params;
  const userId = await getUserRowId(clerkUserId);
  const db = getDatabase();
  if (!(await getConversation(db, userId, id))) {
    return createNotFoundResponse();
  }
  return Response.json({ draft: await getDraftAnswers(db, id) });
};

/**
 * `PUT /api/conversations/[id]/answers` with `{ quizId, answers }`: keeps
 * the answers picked so far, without a run. 404 when the conversation is
 * not theirs or has no such quiz.
 */
export const saveDraftAnswersHandler = async (
  request: Request,
  clerkUserId: string,
  { params }: ConversationRouteContext,
): Promise<Response> => {
  const limited = limitWrites(clerkUserId);
  if (limited) {
    return limited;
  }

  const parsed = DraftAnswersSchema.safeParse(await readJson(request));
  if (!parsed.success) {
    return Response.json(
      { error: INVALID_ANSWERS_ERROR },
      { status: BAD_REQUEST_STATUS },
    );
  }

  const { id } = await params;
  const userId = await getUserRowId(clerkUserId);
  const db = getDatabase();
  const isSaved =
    (await getConversation(db, userId, id)) !== null &&
    (await saveDraftAnswers(db, id, parsed.data));
  return isSaved
    ? new Response(null, { status: NO_CONTENT_STATUS })
    : createNotFoundResponse();
};
