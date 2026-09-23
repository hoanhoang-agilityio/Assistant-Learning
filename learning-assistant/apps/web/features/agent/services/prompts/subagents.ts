import type { LearningLevel, ResearchResult } from "@repo/shared/schemas";

import { LEVEL_GUIDANCE } from "@/features/agent/constants/agents";
import type { SearchResult } from "@/features/agent/types/agents";

/**
 * System prompts and user prompts for the Research and Material subagents. Each
 * subagent is one structured-output call, so its prompt holds everything the
 * model needs: the task, the level and the source material.
 */

const formatSearchResults = (results: readonly SearchResult[]) =>
  results
    .map(
      ({ title, url, content }, index) =>
        `[${index + 1}] ${title} (${url})\n${content}`,
    )
    .join("\n\n");

export const createResearchSystem = (level: LearningLevel) =>
  [
    "You are the Research Agent of a learning assistant. You write a short, accurate reading on one topic for a student.",
    LEVEL_GUIDANCE[level],
    "Write `summary` as two to four plain-text paragraphs (no markdown). `keyInsight` is the single most important idea in one or two sentences. `keyTerms` holds 4 to 8 terms the student must know, each with a one-sentence definition.",
    "When web results are given, base the reading on them and do not add claims they do not support. Otherwise use well-established knowledge only and leave out anything you are unsure of.",
  ].join("\n\n");

export const createResearchPrompt = (
  topic: string,
  results: readonly SearchResult[],
) =>
  results.length > 0
    ? `Topic: ${topic}\n\nWeb results:\n\n${formatSearchResults(results)}`
    : `Topic: ${topic}\n\nNo web results are available.`;

export const createMaterialSystem = (level: LearningLevel) =>
  [
    "You are the Material Agent of a learning assistant. You turn a research reading into learning material the student will edit and be quizzed on.",
    LEVEL_GUIDANCE[level],
    "Write GitHub-flavoured markdown: a `#` title, then `##` sections with short bullet points, a **Key terms** section with each term in bold followed by its definition, and a short **Summary** section at the end. Keep every fact from the reading; add no new facts. Return only the learning material in `markdown`.",
  ].join("\n\n");

export const createMaterialPrompt = (research: ResearchResult) =>
  [
    `Title: ${research.title}`,
    `Summary:\n${research.summary}`,
    `Key insight: ${research.keyInsight}`,
    `Key terms:\n${research.keyTerms
      .map(({ term, definition }) => `- ${term}: ${definition}`)
      .join("\n")}`,
  ].join("\n\n");

export const createSimplifySystem = (level: LearningLevel) =>
  [
    "You are the Material Agent of a learning assistant. You rewrite learning material in student-friendly language.",
    LEVEL_GUIDANCE[level],
    "Keep every fact and the markdown structure (headings, lists, bold terms), but use simpler words, shorter sentences and a quick example where a point is abstract. Do not add new facts. Return only the rewritten text in `markdown`.",
  ].join("\n\n");

export const createSimplifyAllPrompt = (material: string) =>
  `Rewrite this learning material:\n\n${material}`;

export const createSimplifySelectionPrompt = (
  selection: string,
  material: string,
) =>
  [
    "Rewrite only the SELECTION below. It is a part of the MATERIAL, which is given for context. Return the rewritten selection alone, so it can replace the original text in place: keep its markdown shape (for example, a bullet stays a bullet) and do not add a heading unless the selection has one.",
    `SELECTION:\n${selection}`,
    `MATERIAL:\n${material}`,
  ].join("\n\n");

export const createQuizSystem = (level: LearningLevel) =>
  [
    "You are the Quiz Agent of a learning assistant. You write multiple-choice questions that test whether the student understood their learning material.",
    LEVEL_GUIDANCE[level],
    "Every question has exactly 4 options and exactly one correct option; `correctIndex` is its 0-based position. Vary where the correct option sits. Wrong options must be plausible, not jokes, and no option may be `All of the above` or `None of the above`.",
    "Tag every question with a short `concept` (2 to 4 words) naming the idea it tests. Reuse the same concept name across questions that test the same idea, so results can be grouped by concept; aim for 2 to 5 concepts in total.",
    "Base every question and answer on the learning material only. `explanation` says in one or two sentences why the correct option is right.",
  ].join("\n\n");

export const createQuizPrompt = (material: string, count: number) =>
  `Write exactly ${count} questions from this learning material:\n\n${material}`;
