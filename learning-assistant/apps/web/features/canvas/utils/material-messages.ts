import {
  SELECTION_FENCE,
  SIMPLIFY_SELECTION_INTRO,
} from "@/features/canvas/constants/material";

/** The chat message that asks the assistant to simplify a selection. */
export const formatSimplifySelectionMessage = (selection: string): string =>
  `${SIMPLIFY_SELECTION_INTRO}\n${SELECTION_FENCE}\n${selection}\n${SELECTION_FENCE}`;
