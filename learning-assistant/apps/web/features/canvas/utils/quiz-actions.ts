import type {
  QuizActionAvailability,
  QuizActionInput,
} from "@/features/canvas/types/quiz";

/**
 * Which quiz buttons can be pressed. Nothing while the agent runs; Submit once
 * every question is answered; Retake once there is something to clear.
 */
export const getQuizActionAvailability = ({
  answeredCount,
  canSubmit,
  isSubmitted,
  isLocked,
}: QuizActionInput): QuizActionAvailability => ({
  canSubmit: canSubmit && !isSubmitted && !isLocked,
  canRetake: (answeredCount > 0 || isSubmitted) && !isLocked,
  canAskNew: !isLocked,
});
