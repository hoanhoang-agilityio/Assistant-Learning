/** Star ratings on the reflection form, lowest first. */
export const RATING_OPTIONS = [1, 2, 3, 4, 5] as const;

export const MAX_RATING = RATING_OPTIONS.length;

/** The star on each rating button and in a saved reflection. */
export const RATING_STAR = "★";

/** Id of the rating question; its radio group points to it. */
export const RATING_LABEL_ID = "reflection-rating-label";
