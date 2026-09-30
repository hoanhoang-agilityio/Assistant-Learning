import {
  FEEDBACK_CATALOG_ID,
  FEEDBACK_SURFACE_ID,
} from "@repo/shared/a2ui/feedback-catalog";
import type { FeedbackComponent } from "@repo/shared/schemas";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { SILENT_RUN_METADATA } from "../../../constants/openai";
import type { EvaluatorInput } from "../../../types/scoring";
import { TEST_RUN_SETTINGS } from "../../__tests__/quiz-fixtures";
import { ScriptedModel } from "../../llm/__tests__/scripted-model";
import { createChatModel } from "../../llm/chat-model";
import { runFeedbackSurface } from "../feedback-surface";

vi.mock("../../llm/chat-model", () => ({ createChatModel: vi.fn() }));

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

/** Makes the Evaluator's model answer each call with the next `render_a2ui` call. */
const replyWith = (...attempts: FeedbackComponent[][]): ScriptedModel => {
  const model = new ScriptedModel((_messages, { index }) => ({
    toolCalls: [
      {
        name: "render_a2ui",
        args: {
          surfaceId: "anything",
          components: attempts[Math.min(index, attempts.length - 1)],
        },
      },
    ],
  }));
  vi.mocked(createChatModel).mockReturnValue(model as never);
  return model;
};

const OPERATIONS = [
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
];

describe("runFeedbackSurface", () => {
  beforeEach(() => vi.mocked(createChatModel).mockReset());

  it("turns a valid render_a2ui call into operations on the app's surface", async () => {
    const model = replyWith(VALID);

    const operations = await runFeedbackSurface({
      input: INPUT,
      settings: TEST_RUN_SETTINGS,
    });

    expect(operations).toEqual(OPERATIONS);
    expect(createChatModel).toHaveBeenCalledWith(TEST_RUN_SETTINGS.apiKey);
    expect(model.boundTools).toEqual(["render_a2ui"]);
    expect(model.boundOptions).toEqual({ tool_choice: "render_a2ui" });
  });

  it("keeps the call out of the chat", async () => {
    const model = replyWith(VALID);
    const stream = vi.spyOn(model, "stream");

    await runFeedbackSurface({ input: INPUT, settings: TEST_RUN_SETTINGS });

    expect(stream.mock.calls[0]?.[1]).toMatchObject({
      metadata: SILENT_RUN_METADATA,
    });
  });

  it("retries once with the validation errors, then succeeds", async () => {
    const dangling = VALID.map((component) =>
      component.component === "FeedbackCard"
        ? { ...component, children: ["chip", "missing"] }
        : component,
    );
    const model = replyWith(dangling, VALID);

    await runFeedbackSurface({ input: INPUT, settings: TEST_RUN_SETTINGS });

    expect(model.calls).toHaveLength(2);
    expect(model.calls[1]?.messages[0]?.text).toContain("missing");
  });

  it("with onDraft, draws the components complete so far as they stream", async () => {
    replyWith(VALID);
    const onDraft = vi.fn();

    const operations = await runFeedbackSurface({
      input: INPUT,
      settings: TEST_RUN_SETTINGS,
      onDraft,
    });

    const drafts = onDraft.mock.calls.map(([draft]) => draft);
    // The root and the chip are written, the step list is not yet.
    expect(drafts).toContainEqual([
      OPERATIONS[0],
      {
        version: "v0.9",
        updateComponents: {
          surfaceId: FEEDBACK_SURFACE_ID,
          components: [{ ...VALID[0], children: ["chip"] }, VALID[1]],
        },
      },
    ]);
    expect(drafts.at(-1)).toEqual(operations);
  });

  it("throws when no attempt produces a valid surface", async () => {
    const noRoot = VALID.map((component) => ({
      ...component,
      id: `x-${component.id}`,
    }));
    replyWith(noRoot);

    await expect(
      runFeedbackSurface({ input: INPUT, settings: TEST_RUN_SETTINGS }),
    ).rejects.toThrow("invalid after 2 attempts");
  });
});
