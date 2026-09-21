import { QuestionCardView } from "@/features/canvas/components/a2ui/QuestionCardView";
import type { CanvasComponentProps } from "@/features/canvas/types/a2ui";
import {
  readBoolean,
  readList,
  readNumber,
  readQuestionResult,
  readText,
} from "@/features/canvas/utils/a2ui-props";
import { createSelectAnswerAction } from "@/features/canvas/utils/quiz-answers";

/**
 * One quiz question, bound to one item of `/questions`. Picking an option
 * dispatches `select_answer`; the Quiz stage writes it to the agent's state.
 */
export const QuestionCard = ({
  props,
  dispatch,
}: CanvasComponentProps<"QuestionCard">) => {
  const questionId = readText(props.questionId);
  const result = readQuestionResult(props.result);

  const handleSelect = (optionIndex: number) => {
    dispatch?.(createSelectAnswerAction({ questionId, optionIndex }));
  };

  return (
    <QuestionCardView
      number={readNumber(props.number) ?? 0}
      concept={readText(props.concept)}
      question={readText(props.question)}
      options={readList<string>(props.options)}
      selectedIndex={readNumber(props.selectedIndex)}
      result={result}
      isDisabled={readBoolean(props.isLocked) || result !== null}
      onSelect={handleSelect}
    />
  );
};
