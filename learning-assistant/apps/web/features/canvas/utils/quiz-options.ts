import type { OptionState, QuestionResult } from "@/features/canvas/types/a2ui";

/**
 * How an option is drawn. Before grading only the choice is marked; after,
 * the correct option is green and a wrong choice is red.
 */
export const getOptionState = (
  index: number,
  selectedIndex: number | null,
  result: QuestionResult | null,
): OptionState => {
  const isSelected = index === selectedIndex;
  if (!result) {
    return isSelected ? "selected" : "idle";
  }
  if (index === result.correctIndex) {
    return "correct";
  }
  return isSelected ? "incorrect" : "idle";
};
