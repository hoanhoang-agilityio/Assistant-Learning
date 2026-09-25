import { FEEDBACK_CATALOG } from "@repo/shared/a2ui/feedback-catalog";
import { MASTERED_PERCENT } from "@repo/shared/constants/scoring";
import { type LearningLevel, OPTION_LETTERS } from "@repo/shared/schemas";

import { LEVEL_GUIDANCE } from "../../constants/agents";
import type { EvaluatorInput, GradedQuestion } from "../../types/scoring";

/**
 * Prompts for the Evaluator Agent. The quiz is graded in code before either
 * call, so both prompts hand the model the grading as fact: it explains and
 * advises, it never re-grades.
 */

const formatOption = (options: readonly string[], index: number | null) =>
  index === null
    ? "no answer"
    : `${OPTION_LETTERS[index] ?? index + 1}) ${options[index] ?? ""}`;

const formatQuestion = (
  {
    qid,
    concept,
    question,
    options,
    chosenIndex,
    correctIndex,
    isCorrect,
  }: GradedQuestion,
  index: number,
) =>
  [
    `Question ${index + 1} (qid: ${qid}, concept: ${concept}) — ${isCorrect ? "CORRECT" : "WRONG"}`,
    question,
    ...options.map((_, option) => `  ${formatOption(options, option)}`),
    `Student chose: ${formatOption(options, chosenIndex)}`,
    `Correct answer: ${formatOption(options, correctIndex)}`,
  ].join("\n");

const formatResult = ({ score, tier }: EvaluatorInput) =>
  [
    `Score: ${score.correct} of ${score.total} correct (${score.percent}%), tier ${tier}.`,
    `Weakest concept: ${score.weakestConcept ?? "none (every concept answered perfectly)"}.`,
    `Mastery by concept:\n${score.mastery
      .map(({ concept, percent }) => `- ${concept}: ${percent}%`)
      .join("\n")}`,
  ].join("\n");

export const createEvaluatorSystem = (level: LearningLevel) =>
  [
    "You are the Evaluator Agent of a learning assistant. A student just took a multiple-choice quiz on their learning material. The quiz is already graded; the grades are final, so never question or change them.",
    LEVEL_GUIDANCE[level],
    "For every question write `explanation`, keyed by its `qid`: one or two sentences on why the correct option is right. When the student chose wrong, first say in a few words why their choice does not fit. Base it on the learning material.",
    "Write `summary` as three to five plain-text sentences (no markdown) addressed to the student: what they did well, the weakest concept and why it matters, and exactly what to review in their learning material next. Be warm and specific, not generic.",
  ].join("\n\n");

export const createEvaluatorPrompt = (input: EvaluatorInput) =>
  [
    formatResult(input),
    `Questions:\n\n${input.questions.map(formatQuestion).join("\n\n")}`,
    `Learning material:\n\n${input.material}`,
  ].join("\n\n");

export const createFeedbackSurfaceSystem = (level: LearningLevel) =>
  [
    "You are the Evaluator Agent of a learning assistant. You compose the student's personal feedback card by calling `render_a2ui` exactly once. The quiz is already graded; use the numbers you are given exactly.",
    LEVEL_GUIDANCE[level],
    [
      "Build a flat list of components from this catalog only:",
      JSON.stringify(FEEDBACK_CATALOG.components),
    ].join("\n"),
    [
      "Rules:",
      '- Exactly one FeedbackCard, with id "root". Its `children` lists the id of every other component, in display order.',
      "- One ConceptChip per concept, in the order given, with the exact concept name and percent; isWeakest is true only for the weakest concept.",
      `- One ReviewLink for the weakest concept, plus at most one more for another concept under ${MASTERED_PERCENT}%. None when every concept is at 100%.`,
      "- One NextStepList with two to four short, concrete steps that follow from the results (e.g. re-read a section, retake the quiz, ask for new questions, simplify the learning material).",
      "- Every id is unique. Use literal values only; no data bindings.",
      "- The FeedbackCard body is two to four plain-text sentences: what went well and what to focus on.",
    ].join("\n"),
  ].join("\n\n");

export const createFeedbackSurfacePrompt = (input: EvaluatorInput) =>
  [
    formatResult(input),
    `Questions the student got wrong:\n${
      input.questions
        .filter(({ isCorrect }) => !isCorrect)
        .map(({ concept, question }) => `- [${concept}] ${question}`)
        .join("\n") || "- none"
    }`,
    `Learning material:\n\n${input.material}`,
  ].join("\n\n");
