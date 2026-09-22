import {
  type LearningState,
  type Notes,
  QUIZ_STATE_KEYS,
  STAGES,
} from "@repo/shared/schemas";

import { getActiveNotes, hasQuizData } from "@/utils/learning-state";

const NOTES_STAGE_INDEX = STAGES.indexOf("notes");

const writeActiveNotes = (notes: Notes, text: string): Notes =>
  notes.view === "simplified" && notes.simplified !== null
    ? { ...notes, simplified: text }
    : { ...notes, original: text };

/**
 * The student edited the notes they are viewing. The quiz was written from
 * the old notes, so it and everything built from it is cleared, `quizOutdated`
 * is set for the banner, and a later stage falls back to Notes. Returns the
 * same state when nothing changed.
 */
export const applyNotesEdit = (
  state: LearningState,
  text: string,
): LearningState => {
  if (!state.notes || getActiveNotes(state.notes) === text) {
    return state;
  }

  return {
    ...state,
    ...Object.fromEntries(QUIZ_STATE_KEYS.map((key) => [key, null])),
    notes: writeActiveNotes(state.notes, text),
    stage:
      STAGES.indexOf(state.stage) > NOTES_STAGE_INDEX ? "notes" : state.stage,
    quizOutdated: state.quizOutdated || hasQuizData(state),
  };
};

/** Switches between the original and simplified notes; changes no content. */
export const setNotesView = (
  state: LearningState,
  view: Notes["view"],
): LearningState =>
  state.notes && state.notes.view !== view
    ? { ...state, notes: { ...state.notes, view } }
    : state;
