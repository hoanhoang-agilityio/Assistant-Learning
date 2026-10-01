import { PROFILE_FIELDS } from "@repo/shared/schemas";

/** The memory API: what is kept about the student (E5). */
export const MEMORY_API_PATH = "/api/memory";

/** What `DELETE /api/memory/[kind]/[id]` forgets one of: a profile field, a concept or a topic. */
export const MEMORY_ITEM_KINDS = ["profile", "concepts", "topics"] as const;

export const BAD_REQUEST_STATUS = 400;
export const INVALID_PROFILE_ERROR = `Send ${PROFILE_FIELDS.join(", ")} or some of them; null forgets one.`;

export const MEMORY_NOT_FOUND_STATUS = 404;
export const MEMORY_NOT_FOUND_ERROR = "Nothing like that is kept.";

export const NO_CONTENT_STATUS = 204;
