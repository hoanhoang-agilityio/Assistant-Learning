import {
  type LearningState,
  type Material,
  QUIZ_STATE_KEYS,
  STAGES,
} from "@repo/shared/schemas";
import {
  getActiveMaterial,
  hasQuizData,
} from "@repo/shared/utils/learning-state";

const MATERIAL_STAGE_INDEX = STAGES.indexOf("material");

const writeActiveMaterial = (material: Material, text: string): Material =>
  material.view === "simplified" && material.simplified !== null
    ? { ...material, simplified: text }
    : { ...material, original: text };

/**
 * The student edited the learning material they are viewing. The quiz was written from
 * the old learning material, so it and everything built from it is cleared, `quizOutdated`
 * is set for the banner, and a later stage falls back to Learning Material. Returns the
 * same state when nothing changed.
 */
export const applyMaterialEdit = (
  state: LearningState,
  text: string,
): LearningState => {
  if (!state.material || getActiveMaterial(state.material) === text) {
    return state;
  }

  return {
    ...state,
    ...Object.fromEntries(QUIZ_STATE_KEYS.map((key) => [key, null])),
    material: writeActiveMaterial(state.material, text),
    stage:
      STAGES.indexOf(state.stage) > MATERIAL_STAGE_INDEX
        ? "material"
        : state.stage,
    quizOutdated: state.quizOutdated || hasQuizData(state),
  };
};

/** Switches between the original and simplified learning material; changes no content. */
export const setMaterialView = (
  state: LearningState,
  view: Material["view"],
): LearningState =>
  state.material && state.material.view !== view
    ? { ...state, material: { ...state.material, view } }
    : state;
