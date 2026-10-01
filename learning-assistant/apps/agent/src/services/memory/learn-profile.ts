import type { ProfileUpdate } from "@repo/shared/schemas";

import { ProfileObservationSchema } from "../../schemas/memory";
import type { ProfileLearnerInput } from "../../types/memory";
import { toProfileUpdate } from "../../utils/student-memory";
import { createProfilePrompt, PROFILE_SYSTEM } from "../prompts/memory";
import { generateStructured } from "../subagents/generate-structured";

interface LearnProfileParams extends ProfileLearnerInput {
  apiKey: string;
}

/**
 * What the student's message says about them as a learner (E2): the profile
 * fields it changes, or `null` when it changes none.
 */
export const learnProfile = async ({
  apiKey,
  settings,
  profile,
  userText,
}: LearnProfileParams): Promise<ProfileUpdate | null> => {
  const observation = await generateStructured({
    settings: { ...settings, apiKey },
    system: PROFILE_SYSTEM,
    prompt: createProfilePrompt(profile, userText),
    schema: ProfileObservationSchema,
  });
  return toProfileUpdate(profile, observation);
};
