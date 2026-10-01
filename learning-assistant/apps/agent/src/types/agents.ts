import type {
  BoardSurface,
  Evaluation,
  Material,
  Score,
  Settings,
  Stage,
  Status,
} from "@repo/shared/schemas";

/** A web search result given to the Research Agent. */
export interface SearchResult {
  title: string;
  url: string;
  content: string;
}

/**
 * The state the Supervisor LLM sees. It never holds the full learning material or quiz,
 * because the whole of it is written into the system prompt on every call.
 */
export interface SupervisorState {
  /** The user's settings the Supervisor must respect. */
  settings: Pick<Settings, "questionCount" | "learningLevel">;
  stage: Stage;
  status: Status;
  topic: string | null;
  research: { title: string; keyInsight: string } | null;
  material: {
    view: Material["view"];
    hasSimplified: boolean;
    characters: number;
  } | null;
  quiz: {
    questionCount: number;
    answeredCount: number;
    submitted: boolean;
  } | null;
  /** The grade in brief; the explanations and feedback stay on the canvas. */
  evaluation: Pick<Evaluation, "correct" | "total" | "weakestConcept"> | null;
  score: Score | null;
  hasFeedback: boolean;
  hasReflection: boolean;
  quizOutdated: boolean;
  /** Board views by name; their components stay on the canvas. */
  board: Pick<BoardSurface, "id" | "title">[];
}
