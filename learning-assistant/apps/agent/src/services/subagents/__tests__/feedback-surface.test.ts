import {
  FEEDBACK_CATALOG_ID,
  FEEDBACK_SURFACE_ID,
} from "@repo/shared/a2ui/feedback-catalog";
import type { FeedbackComponent } from "@repo/shared/schemas";
import { generateText, streamText } from "ai";
import { beforeEach, describe, expect, it, vi } from "vitest";

import type { EvaluatorInput } from "../../../types/scoring";
import { TEST_RUN_SETTINGS } from "../../__tests__/quiz-fixtures";
import { runFeedbackSurface } from "../feedback-surface";

vi.mock("ai", async (importOriginal) => ({
  ...(await importOriginal<typeof import("ai")>()),
  generateText: vi.fn(),
  streamText: vi.fn(),
}));

vi.mock("../../llm/language-model", () => ({
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
  material: "# Scope",
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
      settings: TEST_RUN_SETTINGS,
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

    await runFeedbackSurface({ input: INPUT, settings: TEST_RUN_SETTINGS });

    expect(generateText).toHaveBeenCalledTimes(2);
    expect(vi.mocked(generateText).mock.calls[1]?.[0].system).toContain(
      "missing",
    );
  });

  it("with onDraft, draws the components complete so far as they stream", async () => {
    const args = JSON.stringify({ surfaceId: "anything", components: VALID });
    // Cut after the root and chip, before the step list is written.
    const cut = args.indexOf('{"id":"steps"');
    vi.mocked(streamText).mockReturnValue({
      fullStream: (async function* () {
        yield { type: "tool-input-delta", id: "t1", delta: args.slice(0, cut) };
        yield { type: "tool-input-delta", id: "t1", delta: args.slice(cut) };
      })(),
      toolCalls: Promise.resolve(replyWith(VALID).toolCalls),
    } as never);
    const onDraft = vi.fn();

    const operations = await runFeedbackSurface({
      input: INPUT,
      settings: TEST_RUN_SETTINGS,
      onDraft,
    });

    expect(generateText).not.toHaveBeenCalled();
    expect(onDraft.mock.calls[0]?.[0][1]).toEqual({
      version: "v0.9",
      updateComponents: {
        surfaceId: FEEDBACK_SURFACE_ID,
        components: [{ ...VALID[0], children: ["chip"] }, VALID[1]],
      },
    });
    expect(onDraft.mock.calls.at(-1)?.[0]).toEqual(operations);
  });

  it("throws when no attempt produces a valid surface", async () => {
    const noRoot = VALID.map((component) => ({
      ...component,
      id: `x-${component.id}`,
    }));
    vi.mocked(generateText).mockResolvedValue(replyWith(noRoot));

    await expect(
      runFeedbackSurface({ input: INPUT, settings: TEST_RUN_SETTINGS }),
    ).rejects.toThrow("invalid after 2 attempts");
  });
});
