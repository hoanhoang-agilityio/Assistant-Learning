import type { LearnerProfile, StudentMemory } from "../schemas/memory";

/** Longest explanation style the profile keeps. */
export const PROFILE_STYLE_MAX_LENGTH = 160;

/** Longest language name the profile keeps. */
export const PROFILE_LANGUAGE_MAX_LENGTH = 40;

/** Under this mastery a concept counts as one the student found hard. */
export const WEAK_CONCEPT_PERCENT = 70;

/** A profile nothing has been learned about yet. */
export const EMPTY_PROFILE: LearnerProfile = {
  level: null,
  style: null,
  language: null,
};

/** A student nothing is kept about yet. */
export const EMPTY_STUDENT_MEMORY: StudentMemory = {
  profile: EMPTY_PROFILE,
  concepts: [],
  topics: [],
};
