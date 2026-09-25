import { type BaseEvent, EventType } from "@ag-ui/client";
import { CONFIRM_NEW_TOPIC_TOOL } from "@repo/shared/constants/agents";
import {
  initialLearningState,
  type LearningState,
  TopicConfirmationRequiredSchema,
} from "@repo/shared/schemas";
import { firstValueFrom, from, toArray } from "rxjs";
import { beforeEach, describe, expect, it, vi } from "vitest";

import type { SupervisorRunContext } from "../../types/agents";
import { syncStateFromTools } from "../state-sync";
import { runResearch } from "../subagents/research";
import { createLearningTools } from "../tools/learning-tools";
import {
  createTestContext,
  RUN_FINISHED,
  RUN_STARTED,
  STATE_WITH_MATERIAL,
} from "./quiz-fixtures";

const RESEARCH = {
  title: "Black holes",
  summary: "Regions where gravity traps light.",
  keyInsight: "Nothing escapes past the event horizon.",
  keyTerms: [],
  sources: [],
};

vi.mock("../subagents/research", () => ({
  runResearch: vi.fn(async () => RESEARCH),
}));

const TOPIC = "Black holes";

const STATE_WITH_GRADED_QUIZ: LearningState = {
  ...initialLearningState,
  topic: "Closures",
  score: { percent: 80, tier: "Master" },
};

const research = (ctx: SupervisorRunContext) =>
  createLearningTools(ctx)
    .find(({ name }) => name === "research")
    ?.execute?.({ topic: TOPIC });

/** Runs `research` the way the Supervisor would, through the state sync. */
const researchThroughSync = async (initial: LearningState) => {
  const { ctx } = createTestContext(initial);
  const result = await research(ctx);
  const states: LearningState[] = [];
  const events = await firstValueFrom(
    from([
      RUN_STARTED,
      {
        type: EventType.TOOL_CALL_START,
        toolCallId: "c1",
        toolCallName: "research",
      } as BaseEvent,
      {
        type: EventType.TOOL_CALL_RESULT,
        messageId: "m1",
        toolCallId: "c1",
        content: JSON.stringify(result),
      } as BaseEvent,
      RUN_FINISHED,
    ]).pipe(
      syncStateFromTools(initial, (state) => states.push(state)),
      toArray(),
    ),
  );
  return { result, events, states };
};

describe("research while work exists", () => {
  beforeEach(() => {
    vi.mocked(runResearch).mockClear();
  });

  it.each([
    ["learning material", STATE_WITH_MATERIAL],
    ["a graded quiz", STATE_WITH_GRADED_QUIZ],
  ])("refuses with %s and asks for confirmNewTopic", async (_, state) => {
    const { ctx } = createTestContext(state);
    const result = await research(ctx);

    expect(runResearch).not.toHaveBeenCalled();
    expect(TopicConfirmationRequiredSchema.parse(result)).toMatchObject({
      ok: false,
      requires: CONFIRM_NEW_TOPIC_TOOL,
      topic: TOPIC,
    });
    expect(JSON.stringify(result)).toContain(CONFIRM_NEW_TOPIC_TOOL);
  });

  it("leaves the state untouched when it refuses", async () => {
    const { events, states } = await researchThroughSync(STATE_WITH_MATERIAL);

    expect(events.map(({ type }) => type)).not.toContain(EventType.STATE_DELTA);
    expect(states).toEqual([]);
  });

  it("researches from an empty state", async () => {
    const { result, states } = await researchThroughSync(initialLearningState);

    expect(runResearch).toHaveBeenCalledOnce();
    expect(result).toEqual({
      ok: true,
      data: { topic: TOPIC, research: RESEARCH },
    });
    expect(states.at(-1)).toMatchObject({
      topic: TOPIC,
      research: RESEARCH,
      status: { running: null },
    });
  });

  it("researches once a confirmed switch cleared the state", async () => {
    const { ctx, setState } = createTestContext(STATE_WITH_MATERIAL);
    setState(initialLearningState);

    const result = await research(ctx);

    expect(runResearch).toHaveBeenCalledOnce();
    expect(result).toMatchObject({ ok: true });
  });
});
