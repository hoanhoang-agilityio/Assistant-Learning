import {
  type LearningState,
  type Material,
  QUIZ_STATE_KEYS,
  STAGES,
} from "../schemas";
import {
  getActiveMaterial,
  hasQuizData,
  writeActiveMaterial,
} from "./learning-state";

/**
 * What the student changes on the canvas without a tool: the learning
 * material's text and view, and a retake. The browser applies these to its
 * own copy of the state at once; the server applies the same functions when
 * the next run starts, from the few fields it lets the browser write.
 */

const MATERIAL_STAGE_INDEX = STAGES.indexOf("material");

const hasSameText = (a: Material, b: Material): boolean =>
  a.original === b.original && a.simplified === b.simplified;

/**
 * Puts `material` in place of the learning material in `state`. When its
 * text differs, the quiz was written from the old text, so the quiz and
 * everything built from it is cleared, `quizOutdated` is set for the banner,
 * and a later stage falls back to Learning Material. A change of view alone
 * changes nothing else. Returns the same state when there is no learning
 * material to replace or nothing changed.
 */
export const replaceMaterial = (
  state: LearningState,
  material: Material,
): LearningState => {
  if (!state.material) {
    return state;
  }
  if (hasSameText(state.material, material)) {
    return state.material.view === material.view
      ? state
      : { ...state, material };
  }

  return {
    ...state,
    ...Object.fromEntries(QUIZ_STATE_KEYS.map((key) => [key, null])),
    material,
    stage:
      STAGES.indexOf(state.stage) > MATERIAL_STAGE_INDEX
        ? "material"
        : state.stage,
    quizOutdated: state.quizOutdated || hasQuizData(state),
  };
};

/**
 * The student edited the learning material they are viewing (see
 * `replaceMaterial` for what follows). Returns the same state when nothing
 * changed.
 */
export const applyMaterialEdit = (
  state: LearningState,
  text: string,
): LearningState =>
  !state.material || getActiveMaterial(state.material) === text
    ? state
    : replaceMaterial(state, writeActiveMaterial(state.material, text));

/** Switches between the original and simplified learning material; changes no content. */
export const setMaterialView = (
  state: LearningState,
  view: Material["view"],
): LearningState =>
  state.material && state.material.view !== view
    ? { ...state, material: { ...state.material, view } }
    : state;

/**
 * Retake: the same questions with no answers. The last attempt's results are
 * cleared and the canvas goes back to the Quiz stage.
 */
export const retakeQuiz = (state: LearningState): LearningState => {
  const { quiz } = state;
  if (!quiz) {
    return state;
  }

  return {
    ...state,
    ...Object.fromEntries(
      QUIZ_STATE_KEYS.filter((key) => key !== "quiz").map((key) => [key, null]),
    ),
    quiz: { ...quiz, answers: {}, submitted: false },
    stage: "quiz",
  };
};
