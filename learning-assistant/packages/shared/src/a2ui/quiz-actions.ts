/**
 * A2UI action names on the Quiz surface. `submit_quiz` reaches the agent in
 * `forwardedProps.a2uiAction`; the others are handled on the client. The
 * quiz template (`templates/quiz.json`) spells the same names.
 */
export const QUIZ_ACTIONS = {
  selectAnswer: "select_answer",
  submit: "submit_quiz",
  retake: "retake_quiz",
  newQuestions: "new_questions",
} as const;

export type QuizActionName = (typeof QUIZ_ACTIONS)[keyof typeof QUIZ_ACTIONS];
