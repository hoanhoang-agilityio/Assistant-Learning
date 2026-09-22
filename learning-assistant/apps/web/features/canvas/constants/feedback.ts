/** Star ratings on the reflection form, lowest first. */
export const RATING_OPTIONS = [1, 2, 3, 4, 5] as const;

export const MAX_RATING = RATING_OPTIONS.length;

/** The version every A2UI operation in `feedback.a2uiOperations` carries. */
export const FEEDBACK_A2UI_VERSION = "v0.9";

/** Top-level keys of the A2UI operations the Feedback surface accepts. */
export const FEEDBACK_OPERATION_KEYS = [
  "createSurface",
  "updateComponents",
  "updateDataModel",
] as const;

/** The star on each rating button and in a saved reflection. */
export const RATING_STAR = "★";

/** Id of the rating question; its radio group points to it. */
export const RATING_LABEL_ID = "reflection-rating-label";
