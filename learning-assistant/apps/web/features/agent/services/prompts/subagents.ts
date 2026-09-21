import type { LearningLevel, ResearchResult } from "@repo/shared/schemas";

import { LEVEL_GUIDANCE } from "@/features/agent/constants/agents";
import type { SearchResult } from "@/features/agent/types/agents";

/**
 * System prompts and user prompts for the Research and Notes subagents. Each
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

export const createNotesSystem = (level: LearningLevel) =>
  [
    "You are the Notes Agent of a learning assistant. You turn a research reading into study notes the student will edit and be quizzed on.",
    LEVEL_GUIDANCE[level],
    "Write GitHub-flavoured markdown: a `#` title, then `##` sections with short bullet points, a **Key terms** section with each term in bold followed by its definition, and a short **Summary** section at the end. Keep every fact from the reading; add no new facts. Return only the notes in `markdown`.",
  ].join("\n\n");

export const createNotesPrompt = (research: ResearchResult) =>
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
    "You are the Notes Agent of a learning assistant. You rewrite study notes in student-friendly language.",
    LEVEL_GUIDANCE[level],
    "Keep every fact and the markdown structure (headings, lists, bold terms), but use simpler words, shorter sentences and a quick example where a point is abstract. Do not add new facts. Return only the rewritten text in `markdown`.",
  ].join("\n\n");

export const createSimplifyAllPrompt = (notes: string) =>
  `Rewrite these notes:\n\n${notes}`;

export const createSimplifySelectionPrompt = (
  selection: string,
  notes: string,
) =>
  [
    "Rewrite only the SELECTION below. It is a part of the NOTES, which are given for context. Return the rewritten selection alone, so it can replace the original text in place: keep its markdown shape (for example, a bullet stays a bullet) and do not add a heading unless the selection has one.",
    `SELECTION:\n${selection}`,
    `NOTES:\n${notes}`,
  ].join("\n\n");
