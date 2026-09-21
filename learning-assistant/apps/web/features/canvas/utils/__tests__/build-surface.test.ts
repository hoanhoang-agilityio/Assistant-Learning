import { extendsBasicCatalog } from "@copilotkit/a2ui-renderer";
import { ROOT_COMPONENT_ID } from "@repo/shared/a2ui/canvas-catalog";
import { QUIZ_ACTIONS } from "@repo/shared/a2ui/quiz-actions";
import { QUIZ_TEMPLATE, RESEARCH_TEMPLATE } from "@repo/shared/a2ui/templates";
import type { Evaluation, Quiz, ResearchResult } from "@repo/shared/schemas";
import { describe, expect, it } from "vitest";

import { CANVAS_CATALOG } from "@/features/canvas/constants/a2ui-catalog";
import {
  buildSurface,
  createQuizDataModel,
  createResearchDataModel,
} from "@/features/canvas/utils/build-surface";

const research: ResearchResult = {
  title: "Photosynthesis",
  summary: "Plants turn light into chemical energy.",
  keyInsight: "Light energy is stored as sugar.",
  keyTerms: [{ term: "Chlorophyll", definition: "The green pigment." }],
  sources: [{ title: "Wikipedia", url: "https://en.wikipedia.org/wiki/P" }],
};

/** Every `{ "path": … }` binding anywhere in a value. */
const collectBindingPaths = (value: unknown): string[] => {
  if (Array.isArray(value)) return value.flatMap(collectBindingPaths);
  if (!value || typeof value !== "object") return [];
  if ("path" in value && typeof value.path === "string") return [value.path];
  return Object.values(value).flatMap(collectBindingPaths);
};

/** Resolves a JSON Pointer such as `/research/title`. */
const resolvePointer = (data: unknown, pointer: string): unknown =>
  pointer
    .split("/")
    .slice(1)
    .reduce<unknown>(
      (node, key) =>
        node && typeof node === "object"
          ? (node as Record<string, unknown>)[key]
          : undefined,
      data,
    );

describe("buildSurface", () => {
  const messages = buildSurface(
    RESEARCH_TEMPLATE,
    createResearchDataModel(research),
  );

  it("creates the surface, then its components, then its data", () => {
    expect(messages.map((message) => Object.keys(message)[1])).toEqual([
      "createSurface",
      "updateComponents",
      "updateDataModel",
    ]);
    expect(messages.every(({ version }) => version === "v0.9")).toBe(true);
  });

  it("uses the template's surface and catalog ids", () => {
    expect(messages[0]).toEqual({
      version: "v0.9",
      createSurface: {
        surfaceId: RESEARCH_TEMPLATE.surfaceId,
        catalogId: CANVAS_CATALOG.id,
      },
    });
  });

  it("binds every template path to research data", () => {
    const dataModel = createResearchDataModel(research);
    const paths = collectBindingPaths(RESEARCH_TEMPLATE.components);

    expect(paths).toEqual([
      "/research/title",
      "/research/summary",
      "/research/keyInsight",
      "/research/keyTerms",
      "/research/sources",
    ]);
    for (const path of paths) {
      expect(resolvePointer(dataModel, path), path).toBeDefined();
    }
    expect(resolvePointer(dataModel, "/research/keyTerms")).toBe(
      research.keyTerms,
    );
  });
});

describe("research template", () => {
  const ids = RESEARCH_TEMPLATE.components.map(({ id }) => id);

  it("has a root and unique component ids", () => {
    expect(ids).toContain(ROOT_COMPONENT_ID);
    expect(new Set(ids).size).toBe(ids.length);
  });

  it("only uses components from the canvas catalog", () => {
    for (const { component } of RESEARCH_TEMPLATE.components) {
      expect(CANVAS_CATALOG.components.has(component), component).toBe(true);
    }
  });

  it("only refers to child ids that exist", () => {
    const childIds = RESEARCH_TEMPLATE.components.flatMap((component) => [
      ...(Array.isArray(component.children) ? component.children : []),
      ...(typeof component.child === "string" ? [component.child] : []),
    ]);
    for (const id of childIds) expect(ids).toContain(id);
  });
});

const OPTIONS = ["a", "b", "c", "d"];

const quiz: Quiz = {
  id: "quiz-1",
  questions: [
    { id: "q1", concept: "Light", question: "One?", options: OPTIONS },
    { id: "q2", concept: "Sugar", question: "Two?", options: OPTIONS },
  ],
  answers: { q1: 2 },
  answerKeySealed: "sealed",
  submitted: false,
};

const evaluation: Evaluation = {
  correct: 1,
  total: 2,
  percent: 50,
  weakestConcept: "Sugar",
  perQuestion: [
    { qid: "q1", correctIndex: 2, isCorrect: true, explanation: "Yes." },
    { qid: "q2", correctIndex: 0, isCorrect: false, explanation: "No." },
  ],
  mastery: [],
};

/** Every action event name anywhere in a value. */
const collectActionNames = (value: unknown): string[] => {
  if (Array.isArray(value)) return value.flatMap(collectActionNames);
  if (!value || typeof value !== "object") return [];
  if ("event" in value && value.event && typeof value.event === "object") {
    return "name" in value.event && typeof value.event.name === "string"
      ? [value.event.name]
      : [];
  }
  return Object.values(value).flatMap(collectActionNames);
};

describe("createQuizDataModel", () => {
  it("holds each question with the student's choice, and no results", () => {
    const model = createQuizDataModel(quiz, null, false);

    expect(model.questions).toEqual([
      { ...quiz.questions[0], number: 1, selectedIndex: 2, result: null },
      { ...quiz.questions[1], number: 2, selectedIndex: null, result: null },
    ]);
    expect(model).toMatchObject({
      quizId: "quiz-1",
      answers: { q1: 2 },
      answeredCount: 1,
      total: 2,
      canSubmit: false,
      isSubmitted: false,
    });
  });

  it("allows Submit once every question is answered", () => {
    const answered = { ...quiz, answers: { q1: 2, q2: 1 } };
    expect(createQuizDataModel(answered, null, false).canSubmit).toBe(true);
  });

  it("ignores an evaluation until the quiz is submitted", () => {
    const model = createQuizDataModel(quiz, evaluation, false);
    expect(model.questions.every(({ result }) => result === null)).toBe(true);
  });

  it("shows results after submit, and no Submit", () => {
    const submitted = { ...quiz, answers: { q1: 2, q2: 1 }, submitted: true };
    const model = createQuizDataModel(submitted, evaluation, false);

    expect(model.canSubmit).toBe(false);
    expect(model.questions[1]?.result).toEqual({
      correctIndex: 0,
      isCorrect: false,
      explanation: "No.",
    });
  });
});

describe("quiz template", () => {
  const ids = QUIZ_TEMPLATE.components.map(({ id }) => id);
  const model = createQuizDataModel(quiz, null, false);
  const [item] = model.questions;
  const questionCard = QUIZ_TEMPLATE.components.find(
    ({ component }) => component === "QuestionCard",
  );

  it("has a root, unique ids and only canvas components", () => {
    expect(ids).toContain(ROOT_COMPONENT_ID);
    expect(new Set(ids).size).toBe(ids.length);
    for (const { component } of QUIZ_TEMPLATE.components) {
      expect(CANVAS_CATALOG.components.has(component), component).toBe(true);
    }
  });

  it("repeats the question card over /questions", () => {
    const list = QUIZ_TEMPLATE.components.find(({ id }) => id === "questions");
    expect(list?.children).toEqual({
      componentId: questionCard?.id,
      path: "/questions",
    });
  });

  it("binds every path to the quiz data", () => {
    for (const path of collectBindingPaths(QUIZ_TEMPLATE.components)) {
      const value = path.startsWith("/")
        ? resolvePointer(model, path)
        : resolvePointer(item, `/${path}`);
      expect(value, path).not.toBeUndefined();
    }
  });

  it("names its actions like the app handles them", () => {
    expect(collectActionNames(QUIZ_TEMPLATE.components).sort()).toEqual(
      [
        QUIZ_ACTIONS.submit,
        QUIZ_ACTIONS.retake,
        QUIZ_ACTIONS.newQuestions,
      ].sort(),
    );
  });
});

describe("CANVAS_CATALOG", () => {
  it("extends the basic catalog", () => {
    expect(extendsBasicCatalog(CANVAS_CATALOG)).toBe(true);
  });
});
