import type { SubagentTool } from "@repo/shared/schemas";

/** What the Supervisor LLM reads about each subagent tool. */
export const TOOL_DESCRIPTIONS: Record<SubagentTool, string> = {
  research:
    "Research a topic for the student and show the reading, key insight, flashcards and sources on the canvas.",
  makeNotes:
    "Turn the current research into editable markdown study notes on the canvas. Needs research.",
  simplify:
    'Rewrite the notes in student-friendly language. scope "all" rewrites the whole set into the Simplified view; scope "selection" rewrites only `selection`, which must be copied exactly from the notes. Needs notes.',
  generateQuiz: "Write a multiple-choice quiz from the notes. Needs notes.",
  evaluate: "Grade the submitted quiz. Needs a fully answered quiz.",
};

/**
 * Tool failures the Supervisor explains to the student. A missing
 * prerequisite says what to do first.
 */
export const TOOL_ERRORS = {
  noResearch:
    "There is no research yet, so notes cannot be made. Research a topic first.",
  noNotes:
    "There are no notes yet, so there is nothing to simplify. Make notes first.",
  noSelection:
    'Simplifying a selection needs the selected text. Pass it in "selection", or use scope "all".',
  selectionNotFound:
    "The selected text was not found in the notes. It must be copied exactly from the notes the student is viewing.",
  stopped: "The student stopped this step.",
} as const;

/** Prefix for an unexpected failure, followed by the error message. */
export const TOOL_FAILURE_PREFIX: Record<SubagentTool, string> = {
  research: "Research failed",
  makeNotes: "Making notes failed",
  simplify: "Simplifying the notes failed",
  generateQuiz: "Writing the quiz failed",
  evaluate: "Evaluating the quiz failed",
};
