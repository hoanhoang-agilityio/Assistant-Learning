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

/** The text fields of the profile form, in the order they are shown. */
export const PROFILE_TEXT_FIELDS = ["style", "language"] as const;

export const MEMORY_COPY = {
  title: "Memory",
  intro:
    "What the assistant keeps about you across conversations. It reads this at the start of every run; nothing else is kept.",
  back: "Back to the assistant",
  loading: "Loading your memory…",
  loadFailed: "Your memory could not be loaded.",
  retry: "Try again",
  profile: "Profile",
  profileHint:
    "Noticed from what you write, or set here. What you set here stays until you change it; clear a field to forget it.",
  level: "Level",
  levelUnset: "Not set",
  style: "Explanation style",
  stylePlaceholder: "e.g. short answers with analogies",
  language: "Language",
  languagePlaceholder: "e.g. Vietnamese",
  save: "Save profile",
  saving: "Saving…",
  saved: "Profile saved.",
  concepts: "Concepts",
  conceptsHint:
    "Mastery over every graded quiz. Weak ones get extra questions in new quizzes.",
  noConcepts: "Nothing yet. Concepts appear once a quiz is graded.",
  weak: "Weak",
  topics: "Topics",
  topicsHint:
    "One per conversation with a graded quiz. Forgetting one keeps the conversation.",
  noTopics: "Nothing yet. A topic appears once its quiz is graded.",
  best: "Best",
  latest: "latest",
  attempt: "attempt",
  attempts: "attempts",
  forget: "Forget",
  forgetConfirm: "Forget this?",
  cancel: "Cancel",
  forgotten: "Forgotten.",
} as const;
