import { QuizActionBarView } from "@/features/canvas/components/a2ui/QuizActionBarView";
import type { CanvasComponentProps } from "@/features/canvas/types/a2ui";
import {
  readAction,
  readBoolean,
  readNumber,
} from "@/features/canvas/utils/a2ui-props";
import { getQuizActionAvailability } from "@/features/canvas/utils/quiz-actions";

/**
 * Quiz progress and its actions. Submit dispatches `submit_quiz` with the
 * quiz id and answers bound in the template; the others are handled on the
 * client by the Quiz stage.
 */
export const QuizActionBar = ({
  props,
}: CanvasComponentProps<"QuizActionBar">) => {
  const answeredCount = readNumber(props.answeredCount) ?? 0;
  const isSubmitted = readBoolean(props.isSubmitted);
  const { canSubmit, canRetake, canAskNew } = getQuizActionAvailability({
    answeredCount,
    canSubmit: readBoolean(props.canSubmit),
    isSubmitted,
    isLocked: readBoolean(props.isLocked),
  });

  return (
    <QuizActionBarView
      answeredCount={answeredCount}
      total={readNumber(props.total) ?? 0}
      canSubmit={canSubmit}
      canRetake={canRetake}
      canAskNew={canAskNew}
      isSubmitted={isSubmitted}
      onSubmit={readAction(props.submitAction)}
      onRetake={readAction(props.retakeAction)}
      onNewQuestions={readAction(props.newQuestionsAction)}
    />
  );
};
