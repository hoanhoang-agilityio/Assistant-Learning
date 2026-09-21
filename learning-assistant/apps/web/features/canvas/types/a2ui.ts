import type { PropsOf, RendererProps } from "@copilotkit/a2ui-renderer";
import type { ResearchResult } from "@repo/shared/schemas";
import type { ReactNode } from "react";

import type { CANVAS_COMPONENT_DEFINITIONS } from "@/features/canvas/constants/a2ui-catalog";

export type CanvasComponentName = keyof typeof CANVAS_COMPONENT_DEFINITIONS;

/** What the A2UI renderer passes to a canvas catalog component. */
export type CanvasComponentProps<K extends CanvasComponentName> = RendererProps<
  PropsOf<typeof CANVAS_COMPONENT_DEFINITIONS, K>
>;

/** An A2UI v0.9 server-to-client message, as the renderer processes it. */
export type A2UIMessage = { version: "v0.9" } & (
  | { createSurface: { surfaceId: string; catalogId: string } }
  | { updateComponents: { surfaceId: string; components: object[] } }
  | { updateDataModel: { surfaceId: string; path: string; value: unknown } }
);

export interface ResearchDataModel {
  research: ResearchResult;
}

/** The renderer's `children` also takes the data path of a template item. */
export type BuildChild = (id: string, basePath?: string) => ReactNode;

/** A child to render: its component id, and for template items its data path. */
export interface ChildRef {
  id: string;
  basePath?: string;
}

/** How one question went, shown on its card after submit. */
export interface QuestionResult {
  correctIndex: number;
  isCorrect: boolean;
  explanation: string;
}

export type OptionState = "idle" | "selected" | "correct" | "incorrect";

/** One QuestionCard's data; the template binds to it with relative paths. */
export interface QuizQuestionItem {
  id: string;
  /** 1-based position in the quiz. */
  number: number;
  concept: string;
  question: string;
  options: string[];
  selectedIndex: number | null;
  /** `null` until the quiz is graded. */
  result: QuestionResult | null;
}

export interface QuizDataModel {
  quizId: string;
  questions: QuizQuestionItem[];
  /** Sent as the Submit action's context. */
  answers: Record<string, number>;
  answeredCount: number;
  total: number;
  canSubmit: boolean;
  isSubmitted: boolean;
  /** The agent is running; the quiz waits for it. */
  isLocked: boolean;
}
