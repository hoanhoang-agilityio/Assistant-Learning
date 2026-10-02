import {
  type LearnerProfile,
  LearnerProfileSchema,
  type ProfileUpdate,
  type StudentMemory,
  StudentMemorySchema,
} from "@repo/shared/schemas";
import { z } from "zod";

import { MEMORY_API_PATH } from "@/features/memory/constants/memory";
import type { MemoryItemRef } from "@/features/memory/types/memory";
import { expectOk } from "@/services/expect-ok";

const SavedProfileSchema = z.object({ profile: LearnerProfileSchema });

/** A concept key can hold any character, so the id is encoded. */
const toMemoryItemPath = ({ kind, id }: MemoryItemRef) =>
  `${MEMORY_API_PATH}/${kind}/${encodeURIComponent(id)}`;

/** Everything kept about the signed-in student. */
export const fetchMemory = async (): Promise<StudentMemory> => {
  const response = await expectOk(await fetch(MEMORY_API_PATH));
  return StudentMemorySchema.parse(await response.json());
};

/** Saves the student's own profile edit; returns the profile as kept. */
export const updateProfile = async (
  update: ProfileUpdate,
): Promise<LearnerProfile> => {
  const response = await expectOk(
    await fetch(MEMORY_API_PATH, {
      method: "PATCH",
      headers: { "content-type": "application/json" },
      body: JSON.stringify(update),
    }),
  );
  return SavedProfileSchema.parse(await response.json()).profile;
};

export const forgetMemoryItem = async (item: MemoryItemRef): Promise<void> => {
  await expectOk(await fetch(toMemoryItemPath(item), { method: "DELETE" }));
};
