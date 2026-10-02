import { getDatabase, getLearningHistory } from "@repo/db";
import type { LearningHistory } from "@repo/shared/schemas";

import { getUserRowId } from "@/services/users";

/** The History page's data, for the user of the verified session only. */
export const fetchLearningHistory = async (
  clerkUserId: string,
): Promise<LearningHistory> =>
  getLearningHistory(getDatabase(), await getUserRowId(clerkUserId));
