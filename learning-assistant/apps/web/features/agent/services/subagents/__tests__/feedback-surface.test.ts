import {
  FEEDBACK_CATALOG_ID,
  FEEDBACK_SURFACE_ID,
} from "@repo/shared/a2ui/feedback-catalog";
import type { FeedbackComponent } from "@repo/shared/schemas";
import { generateText } from "ai";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { DEFAULT_SETTINGS } from "@/constants/settings";
import { runFeedbackSurface } from "@/features/agent/services/subagents/feedback-surface";
import type { EvaluatorInput } from "@/features/agent/types/scoring";

vi.mock("ai", async (importOriginal) => ({
  ...(await importOriginal<typeof import("ai")>()),
  generateText: vi.fn(),
}));

vi.mock("@/services/llm/language-model", () => ({
  createLanguageModel: vi.fn(() => ({})),
}));

const INPUT: EvaluatorInput = {
  questions: [],
  score: {
    correct: 1,
    total: 2,
    percent: 50,
    perQuestion: [],
    mastery: [{ concept: "Scope", percent: 50 }],
    weakestConcept: "Scope",
  },
  tier: "Practitioner",
  notes: "# Scope",
};

const VALID: FeedbackComponent[] = [
  {
    id: "root",
    component: "FeedbackCard",
    title: "Nice start",
    body: "Keep going.",
    children: ["chip", "steps"],
  },
  {
    id: "chip",
    component: "ConceptChip",
    concept: "Scope",
    percent: 50,
    isWeakest: true,
  },
  {
    id: "steps",
    component: "NextStepList",
    title: "Next steps",
    steps: ["Re-read Scope"],
  },
];

/** A `generateText` reply whose only tool call has these components. */
const replyWith = (components: FeedbackComponent[]) =>
  ({
    toolCalls: [
      {
        toolName: "render_a2ui",
        input: { surfaceId: "anything", components },
      },
    ],
  }) as unknown as Awaited<ReturnType<typeof generateText>>;

describe("runFeedbackSurface", () => {
  beforeEach(() => vi.mocked(generateText).mockReset());

  it("turns a valid render_a2ui call into operations on the app's surface", async () => {
    vi.mocked(generateText).mockResolvedValue(replyWith(VALID));

    const operations = await runFeedbackSurface({
      input: INPUT,
      settings: DEFAULT_SETTINGS,
    });

    expect(operations).toEqual([
      {
        version: "v0.9",
        createSurface: {
          surfaceId: FEEDBACK_SURFACE_ID,
          catalogId: FEEDBACK_CATALOG_ID,
        },
      },
      {
        version: "v0.9",
        updateComponents: { surfaceId: FEEDBACK_SURFACE_ID, components: VALID },
      },
    ]);
    expect(vi.mocked(generateText).mock.calls[0]?.[0].toolChoice).toEqual({
      type: "tool",
      toolName: "render_a2ui",
    });
  });

  it("retries once with the validation errors, then succeeds", async () => {
    const dangling = VALID.map((component) =>
      component.component === "FeedbackCard"
        ? { ...component, children: ["chip", "missing"] }
        : component,
    );
    vi.mocked(generateText)
      .mockResolvedValueOnce(replyWith(dangling))
      .mockResolvedValueOnce(replyWith(VALID));

    await runFeedbackSurface({ input: INPUT, settings: DEFAULT_SETTINGS });

    expect(generateText).toHaveBeenCalledTimes(2);
    expect(vi.mocked(generateText).mock.calls[1]?.[0].system).toContain(
      "missing",
    );
  });

  it("throws when no attempt produces a valid surface", async () => {
    const noRoot = VALID.map((component) => ({
      ...component,
      id: `x-${component.id}`,
    }));
    vi.mocked(generateText).mockResolvedValue(replyWith(noRoot));

    await expect(
      runFeedbackSurface({ input: INPUT, settings: DEFAULT_SETTINGS }),
    ).rejects.toThrow("invalid after 2 attempts");
  });
});
