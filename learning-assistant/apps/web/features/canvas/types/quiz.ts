/** The context a QuestionCard sends when an option is picked. */
export interface SelectAnswer {
  questionId: string;
  optionIndex: number;
}

/** The quiz surface's state that decides which buttons are enabled. */
export interface QuizActionInput {
  answeredCount: number;
  canSubmit: boolean;
  isSubmitted: boolean;
  isLocked: boolean;
}

export interface QuizActionAvailability {
  canSubmit: boolean;
  canRetake: boolean;
  canAskNew: boolean;
}
