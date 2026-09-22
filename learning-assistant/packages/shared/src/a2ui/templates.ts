import type { SurfaceTemplate } from "./surface-template";
import evaluationTemplate from "./templates/evaluation.json";
import quizTemplate from "./templates/quiz.json";
import researchTemplate from "./templates/research.json";
import scoreTemplate from "./templates/score.json";

/** The Research stage: article, key insight, flashcards and sources. */
export const RESEARCH_TEMPLATE: SurfaceTemplate = researchTemplate;

/** The Quiz stage: one QuestionCard per question, then Submit/Retake/New. */
export const QUIZ_TEMPLATE: SurfaceTemplate = quizTemplate;

/** The Evaluation stage: stat tiles, then mastery bars by concept. */
export const EVALUATION_TEMPLATE: SurfaceTemplate = evaluationTemplate;

/** The Score stage: tier badge, final score and stat chips. */
export const SCORE_TEMPLATE: SurfaceTemplate = scoreTemplate;
