import {
  deleteConceptMemory,
  deleteTopicMemory,
  getDatabase,
  getStudentMemory,
  saveLearnerProfile,
} from "@repo/db";
import { ProfileFieldSchema, ProfileUpdateSchema } from "@repo/shared/schemas";
import { z } from "zod";

import {
  BAD_REQUEST_STATUS,
  INVALID_PROFILE_ERROR,
  MEMORY_ITEM_KINDS,
  MEMORY_NOT_FOUND_ERROR,
  MEMORY_NOT_FOUND_STATUS,
  NO_CONTENT_STATUS,
} from "@/features/memory/constants/memory";
import {
  createTooManyRequestsResponse,
  writeRateLimiter,
} from "@/services/rate-limit";
import { getUserRowId } from "@/services/users";

/** A route under `/api/memory/[kind]/[id]`. */
export interface MemoryItemRouteContext {
  params: Promise<{ kind: string; id: string }>;
}

const MemoryItemKindSchema = z.enum(MEMORY_ITEM_KINDS);

const createNotFoundResponse = (): Response =>
  Response.json(
    { error: MEMORY_NOT_FOUND_ERROR },
    { status: MEMORY_NOT_FOUND_STATUS },
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

/** `GET /api/memory`: the profile, concepts weakest first, topics newest first. */
export const getMemoryHandler = async (
  _request: Request,
  clerkUserId: string,
): Promise<Response> => {
  const userId = await getUserRowId(clerkUserId);
  return Response.json(await getStudentMemory(getDatabase(), userId));
};

/** `PATCH /api/memory` with profile fields: the student's own edit; `null` forgets one. */
export const updateProfileHandler = async (
  request: Request,
  clerkUserId: string,
): Promise<Response> => {
  const limited = limitWrites(clerkUserId);
  if (limited) {
    return limited;
  }

  const parsed = ProfileUpdateSchema.safeParse(await readJson(request));
  if (!parsed.success) {
    return Response.json(
      { error: INVALID_PROFILE_ERROR },
      { status: BAD_REQUEST_STATUS },
    );
  }

  const userId = await getUserRowId(clerkUserId);
  const profile = await saveLearnerProfile(getDatabase(), userId, parsed.data);
  return Response.json({ profile });
};

/** Forgets the item; false when the student has no such item. */
const forgetItem = async (
  userId: string,
  kind: z.infer<typeof MemoryItemKindSchema>,
  id: string,
): Promise<boolean> => {
  const db = getDatabase();
  if (kind === "concepts") {
    return deleteConceptMemory(db, userId, id);
  }
  if (kind === "topics") {
    return deleteTopicMemory(db, userId, id);
  }

  const field = ProfileFieldSchema.safeParse(id);
  if (!field.success) {
    return false;
  }
  await saveLearnerProfile(db, userId, { [field.data]: null });
  return true;
};

/**
 * `DELETE /api/memory/[kind]/[id]`: forgets one profile field (`id` is
 * `level`, `style` or `language`), one concept (its key) or one topic (its
 * conversation's id; the conversation stays). It never reaches the prompt
 * again: each run reads memory afresh.
 */
export const deleteMemoryItemHandler = async (
  _request: Request,
  clerkUserId: string,
  { params }: MemoryItemRouteContext,
): Promise<Response> => {
  const limited = limitWrites(clerkUserId);
  if (limited) {
    return limited;
  }

  const { kind, id } = await params;
  const parsedKind = MemoryItemKindSchema.safeParse(kind);
  if (!parsedKind.success) {
    return createNotFoundResponse();
  }

  const userId = await getUserRowId(clerkUserId);
  return (await forgetItem(userId, parsedKind.data, id))
    ? new Response(null, { status: NO_CONTENT_STATUS })
    : createNotFoundResponse();
};
