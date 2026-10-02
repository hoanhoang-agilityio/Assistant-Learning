import type { LearningLevel } from "@repo/shared/schemas";

import type {
  MEMORY_ITEM_KINDS,
  PROFILE_TEXT_FIELDS,
} from "@/features/memory/constants/memory";

/** What `DELETE /api/memory/[kind]/[id]` forgets one of. */
export type MemoryItemKind = (typeof MEMORY_ITEM_KINDS)[number];

/**
 * One thing kept about the student: a profile field (`id` is the field), a
 * concept (its key) or a topic (its conversation's id).
 */
export interface MemoryItemRef {
  kind: MemoryItemKind;
  id: string;
}

/** A profile field the student types. */
export type ProfileTextField = (typeof PROFILE_TEXT_FIELDS)[number];

/** The profile as the form edits it: an empty text field means "not set". */
export interface ProfileFormValues {
  level: LearningLevel | null;
  style: string;
  language: string;
}
