import type { SubagentTool } from "@repo/shared/schemas";

/** What the Supervisor LLM reads about each subagent tool. */
export const TOOL_DESCRIPTIONS: Record<SubagentTool, string> = {
  research:
    "Research a topic for the student and show the reading, key insight, flashcards and sources on the canvas.",
  makeMaterial:
    "Turn the current research into editable markdown learning material on the canvas. Needs research.",
  simplify:
    'Rewrite the learning material in student-friendly language. scope "all" rewrites the whole set into the Simplified view; scope "selection" rewrites only `selection`, which must be copied exactly from the learning material. Needs learning material.',
  generateQuiz:
    "Write a new multiple-choice quiz from the learning material the student is viewing, replacing any current quiz and its results. Needs learning material.",
  evaluate:
    "Grade the quiz with the answers the student picked on the canvas. Only when they ask in chat to grade it; the Submit button grades it without you. Needs every question answered.",
};

/**
 * Tool failures the Supervisor explains to the student. A missing
 * prerequisite says what to do first.
 */
export const TOOL_ERRORS = {
  noResearch:
    "There is no research yet, so learning material cannot be made. Research a topic first.",
  noMaterial:
    "There is no learning material yet, so there is nothing to simplify. Make learning material first.",
  noSelection:
    'Simplifying a selection needs the selected text. Pass it in "selection", or use scope "all".',
  selectionNotFound:
    "The selected text was not found in the learning material. It must be copied exactly from the learning material the student is viewing.",
  noMaterialForQuiz:
    "There is no learning material yet, so there is nothing to quiz on. Make learning material first.",
  noQuiz: "There is no quiz yet. Write a quiz first.",
  quizAlreadySubmitted:
    "This quiz was already graded. The student can Retake it or ask for new questions.",
  staleQuiz:
    "The answers were for a quiz that has since been replaced. The student should answer the current quiz.",
  stopped: "The student stopped this step.",
} as const;

/** Prefix for an unexpected failure, followed by the error message. */
export const TOOL_FAILURE_PREFIX: Record<SubagentTool, string> = {
  research: "Research failed",
  makeMaterial: "Making learning material failed",
  simplify: "Simplifying the learning material failed",
  generateQuiz: "Writing the quiz failed",
  evaluate: "Evaluating the quiz failed",
};
