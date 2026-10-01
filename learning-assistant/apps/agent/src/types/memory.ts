import type {
  LearnerProfile,
  ProfileUpdate,
  Settings,
  StudentMemory,
} from "@repo/shared/schemas";

/**
 * Where what is kept about a student across conversations lives (E2–E5),
 * by their Clerk id. Concepts and topics are written with each graded
 * attempt, so the agent only reads them; it writes the profile.
 */
export interface LearningMemory {
  load: (userId: string) => Promise<StudentMemory>;
  /** Changes only the profile fields the update names. */
  saveProfile: (userId: string, update: ProfileUpdate) => Promise<void>;
}

/** What a profile learner reads: the profile so far and one message. */
export interface ProfileLearnerInput {
  profile: LearnerProfile;
  /** What the student wrote in the run. */
  userText: string;
  settings: Settings;
}

/** What one message of the student's changes in their profile, or `null`. */
export type ProfileLearner = (
  input: ProfileLearnerInput,
) => Promise<ProfileUpdate | null>;

/** Long-term memory as one run uses it: read before, learned from after. */
export interface RunMemory {
  store: LearningMemory;
  learnProfile: ProfileLearner;
}
