import type { Quiz } from "@repo/shared/schemas";

/** Whether a quiz can be graded, and with which answers. */
export type SubmissionCheck =
  | { ok: true; quiz: Quiz; answers: Quiz["answers"] }
  | { ok: false; error: string };
