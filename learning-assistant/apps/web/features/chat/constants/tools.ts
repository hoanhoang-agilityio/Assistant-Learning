import type { SubagentTool } from "@repo/shared/schemas";

import type { ChatCardKind } from "@/features/chat/types/chat";

/** Progress-card copy for each subagent tool. */
export const TOOL_LABELS: Record<
  SubagentTool,
  { running: string; done: string; failed: string; stopped: string }
> = {
  research: {
    running: "Researching",
    done: "Research ready",
    failed: "Research failed",
    stopped: "Research stopped",
  },
  makeMaterial: {
    running: "Writing learning material",
    done: "Learning material ready",
    failed: "Learning material failed",
    stopped: "Learning material stopped",
  },
  simplify: {
    running: "Simplifying learning material",
    done: "Learning material simplified",
    failed: "Simplify failed",
    stopped: "Simplify stopped",
  },
  generateQuiz: {
    running: "Writing quiz questions",
    done: "Quiz ready",
    failed: "Quiz failed",
    stopped: "Quiz stopped",
  },
  evaluate: {
    running: "Evaluating your answers",
    done: "Evaluation ready",
    failed: "Evaluation failed",
    stopped: "Evaluation stopped",
  },
};

/** The card under a finished evaluation that opens the Feedback stage. */
export const FEEDBACK_READY_COPY = {
  title: "Feedback ready",
  hint: "see your personal feedback",
} as const;

/**
 * What the Supervisor reads about each chat card tool, added after the prefix
 * `useComponent` writes ("Use this tool to display the ... component in the
 * chat"). Each says when to pick that card over the others.
 */
export const CHAT_CARD_DESCRIPTIONS: Record<ChatCardKind, string> = {
  concept:
    "A card that explains one term: its name, a one- or two-sentence " +
    'definition and an optional short example. For "what is X?".',
  comparison:
    "A two-column table comparing two things aspect by aspect, with an " +
    'optional one-line verdict. For "X vs Y" or "what is the difference".',
  steps:
    "A numbered list of steps, each a short title and one sentence. For " +
    '"how does X work" or "how do I do X" when the order matters.',
  codeExample:
    "A short code snippet with its language and a one- or two-sentence " +
    'explanation. For "show me an example" or "how do I write X".',
};

/** The small label above each chat card's title. */
export const CHAT_CARD_LABELS: Record<ChatCardKind, string> = {
  concept: "Concept",
  comparison: "Comparison",
  steps: "Steps",
  codeExample: "Code example",
};

/** Chat card copy for `renderSurface`, by target. */
export const RENDER_SURFACE_COPY = {
  chat: {
    running: "Composing a view",
    done: "View ready",
    stopped: "View stopped",
  },
  canvas: {
    running: "Composing a Board view",
    done: "Added to the Board",
    stopped: "Board view stopped",
  },
} as const;

/** Chat card copy for `updateBoardSurface`. */
export const UPDATE_BOARD_SURFACE_COPY = {
  running: "Updating a Board view",
  done: "Board view updated",
  stopped: "Board update stopped",
} as const;

/** Chat card copy for `deleteBoardSurface`. */
export const DELETE_BOARD_SURFACE_COPY = {
  running: "Removing from the Board",
  done: "Removed from the Board",
  stopped: "Board removal stopped",
} as const;
