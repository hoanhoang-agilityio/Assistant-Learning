import type { SurfaceTemplate } from "./surface-template";
import quizTemplate from "./templates/quiz.json";
import researchTemplate from "./templates/research.json";

/** The Research stage: article, key insight, flashcards and sources. */
export const RESEARCH_TEMPLATE: SurfaceTemplate = researchTemplate;

/** The Quiz stage: one QuestionCard per question, then Submit/Retake/New. */
export const QUIZ_TEMPLATE: SurfaceTemplate = quizTemplate;
