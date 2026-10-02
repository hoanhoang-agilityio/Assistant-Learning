import { WEAK_CONCEPT_PERCENT } from "@repo/shared/constants/memory";
import {
  type ConceptMemory,
  type LearnerProfile,
  ProfileFieldSchema,
  type ProfileUpdate,
  type StudentMemory,
} from "@repo/shared/schemas";

import type {
  MemoryItemRef,
  ProfileFormValues,
} from "@/features/memory/types/memory";

export const toProfileFormValues = ({
  level,
  style,
  language,
}: LearnerProfile): ProfileFormValues => ({
  level,
  style: style ?? "",
  language: language ?? "",
});

const toStoredText = (text: string): string | null => text.trim() || null;

/**
 * What `PATCH /api/memory` needs to make the saved profile match the form:
 * only the fields that changed, a cleared text field as `null` (forget it).
 * `null` when nothing changed.
 */
export const createProfileUpdate = (
  saved: LearnerProfile,
  values: ProfileFormValues,
): ProfileUpdate | null => {
  const next: LearnerProfile = {
    level: values.level,
    style: toStoredText(values.style),
    language: toStoredText(values.language),
  };
  const changed = ProfileFieldSchema.options.filter(
    (field) => next[field] !== saved[field],
  );

  return changed.length > 0
    ? Object.fromEntries(changed.map((field) => [field, next[field]]))
    : null;
};

/** The form with one forgotten field unset, keeping edits to the others. */
export const clearProfileFormField = (
  values: ProfileFormValues,
  id: string,
): ProfileFormValues => {
  const field = ProfileFieldSchema.safeParse(id);
  if (!field.success) {
    return values;
  }
  return field.data === "level"
    ? { ...values, level: null }
    : { ...values, [field.data]: "" };
};

export const isSameMemoryItem = (
  a: MemoryItemRef | null,
  b: MemoryItemRef,
): boolean => a?.kind === b.kind && a.id === b.id;

/** The memory without `item`, as the server keeps it after a forget. */
export const removeMemoryItem = (
  memory: StudentMemory,
  { kind, id }: MemoryItemRef,
): StudentMemory => {
  if (kind === "concepts") {
    return {
      ...memory,
      concepts: memory.concepts.filter(({ key }) => key !== id),
    };
  }
  if (kind === "topics") {
    return {
      ...memory,
      topics: memory.topics.filter(
        ({ conversationId }) => conversationId !== id,
      ),
    };
  }

  const field = ProfileFieldSchema.safeParse(id);
  return field.success
    ? { ...memory, profile: { ...memory.profile, [field.data]: null } }
    : memory;
};

/** A concept the student found hard: the agent quizzes these more. */
export const isWeakConcept = ({ percent }: ConceptMemory): boolean =>
  percent < WEAK_CONCEPT_PERCENT;
