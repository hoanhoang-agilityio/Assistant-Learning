import { type BaseEvent, EventType } from "@ag-ui/client";
import {
  initialLearningState,
  type LearningState,
  type QuizDraft,
} from "@repo/shared/schemas";

import { DEFAULT_SETTINGS } from "@/constants/settings";
import { SealedAnswerKeyStore } from "@/features/agent/services/answer-key/sealed-answer-key-store";
import type { SupervisorRunContext } from "@/features/agent/types/agents";
import type { RunSettings } from "@/types/llm";

/** Text that must never reach the client before the quiz is submitted. */
export const SECRET_EXPLANATION = "SECRET-EXPLANATION";

export const QUIZ_DRAFT: QuizDraft = {
  questions: [0, 1, 2].map((index) => ({
    concept: index === 2 ? "Scope" : "Closures",
    question: `Question ${index + 1}?`,
    options: ["a", "b", "c", "d"],
    correctIndex: index + 1,
    explanation: `${SECRET_EXPLANATION}-${index + 1}`,
  })),
};

export const STATE_WITH_NOTES: LearningState = {
  ...initialLearningState,
  stage: "notes",
  topic: "Closures",
  notes: { original: "# Closures", simplified: null, view: "original" },
};

/** Run settings with a placeholder key; model calls are mocked in tests. */
export const TEST_RUN_SETTINGS: RunSettings = {
  ...DEFAULT_SETTINGS,
  apiKey: "sk-test",
};

/** A run context whose state can be changed by the test, like the wrapper's. */
export const createTestContext = (initial: LearningState) => {
  let state = initial;
  const ctx: SupervisorRunContext = {
    settings: TEST_RUN_SETTINGS,
    getState: () => state,
    signal: new AbortController().signal,
    env: {},
    answerKeys: new SealedAnswerKeyStore("test-secret"),
  };
  return {
    ctx,
    setState: (next: LearningState) => {
      state = next;
    },
  };
};

export const RUN_STARTED = {
  type: EventType.RUN_STARTED,
  threadId: "t1",
  runId: "r1",
} as BaseEvent;

export const RUN_FINISHED = {
  type: EventType.RUN_FINISHED,
  threadId: "t1",
  runId: "r1",
} as BaseEvent;
