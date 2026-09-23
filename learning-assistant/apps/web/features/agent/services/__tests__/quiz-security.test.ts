import { type BaseEvent, EventType, type Message } from "@ag-ui/client";
import { QUIZ_ACTIONS } from "@repo/shared/a2ui/quiz-actions";
import type { LearningState } from "@repo/shared/schemas";
import { firstValueFrom, from, type Observable, of, toArray } from "rxjs";
import { describe, expect, it, vi } from "vitest";

import {
  createTestContext,
  QUIZ_DRAFT,
  RUN_FINISHED,
  RUN_STARTED,
  SECRET_EXPLANATION,
  STATE_WITH_MATERIAL,
} from "@/features/agent/services/__tests__/quiz-fixtures";
import { syncStateFromTools } from "@/features/agent/services/state-sync";
import { runSubmittedQuiz } from "@/features/agent/services/submit-quiz";
import { createQuizTools } from "@/features/agent/services/tools/quiz-tools";
import type { SupervisorRunContext } from "@/features/agent/types/agents";
import { parseSubmitAction } from "@/features/agent/utils/submit-action";

vi.mock("@/features/agent/services/subagents/quiz", () => ({
  runQuiz: vi.fn(async () => QUIZ_DRAFT),
}));

// The Evaluator is unavailable here, so the answer key's explanations and the
// score-based summary are used.
vi.mock("@/features/agent/services/subagents/evaluator", () => ({
  runEvaluator: vi.fn(async () => {
    throw new Error("No model in tests.");
  }),
}));

vi.mock("@/features/agent/services/subagents/feedback-surface", () => ({
  runFeedbackSurface: vi.fn(async () => {
    throw new Error("No model in tests.");
  }),
}));

/** Anything that would reveal the answer key. */
const LEAKS = ["correctIndex", "explanation", SECRET_EXPLANATION];

const collect = (events: BaseEvent[], initial: LearningState) => {
  const states: LearningState[] = [];
  return firstValueFrom(
    from(events).pipe(
      syncStateFromTools(initial, (state) => states.push(state)),
      toArray(),
    ),
  ).then((out) => ({ events: out, states }));
};

/** Runs `generateQuiz` the way the Supervisor would, through the state sync. */
const generateQuiz = async (ctx: SupervisorRunContext) => {
  const tool = createQuizTools(ctx).find(({ name }) => name === "generateQuiz");
  const result = await tool?.execute?.({});

  return collect(
    [
      RUN_STARTED,
      {
        type: EventType.TOOL_CALL_START,
        toolCallId: "c1",
        toolCallName: "generateQuiz",
      } as BaseEvent,
      {
        type: EventType.TOOL_CALL_RESULT,
        messageId: "m1",
        toolCallId: "c1",
        content: JSON.stringify(result),
      } as BaseEvent,
      RUN_FINISHED,
    ],
    ctx.getState(),
  );
};

describe("answer key before submit (M4.7)", () => {
  it("never appears in a tool result, state delta or state", async () => {
    const { ctx } = createTestContext(STATE_WITH_MATERIAL);
    const { events, states } = await generateQuiz(ctx);

    const deltas = events.filter(({ type }) => type === EventType.STATE_DELTA);
    expect(deltas.length).toBeGreaterThan(0);
    expect(states.at(-1)?.quiz?.questions).toHaveLength(3);

    const wire = JSON.stringify({ events, states });
    for (const leak of LEAKS) {
      expect(wire).not.toContain(leak);
    }
  });

  it("is revealed only after Submit, in the evaluation", async () => {
    const { ctx, setState } = createTestContext(STATE_WITH_MATERIAL);
    const { states } = await generateQuiz(ctx);
    const quizzed = states.at(-1);
    if (!quizzed?.quiz) {
      throw new Error("No quiz was written.");
    }
    setState(quizzed);

    const answers = { q1: 1, q2: 0, q3: 3 };
    const submit = parseSubmitAction({
      a2uiAction: {
        userAction: {
          name: QUIZ_ACTIONS.submit,
          context: { quizId: quizzed.quiz.id, answers },
        },
      },
    });
    const runSupervisor = vi.fn<(messages: Message[]) => Observable<BaseEvent>>(
      () => of(RUN_STARTED, RUN_FINISHED),
    );

    const events = await firstValueFrom(
      runSubmittedQuiz({
        input: {
          threadId: "t1",
          runId: "r2",
          state: quizzed,
          messages: [],
          tools: [],
          context: [],
          forwardedProps: {},
        },
        ctx,
        submission: submit?.submission,
        runSupervisor,
      }).pipe(syncStateFromTools(quizzed, setState), toArray()),
    );

    expect(events.map(({ type }) => type)).toEqual([
      EventType.RUN_STARTED,
      EventType.TOOL_CALL_START,
      EventType.STATE_DELTA,
      EventType.TOOL_CALL_ARGS,
      EventType.TOOL_CALL_END,
      EventType.TOOL_CALL_RESULT,
      EventType.STATE_DELTA,
      EventType.RUN_FINISHED,
    ]);

    const graded = ctx.getState();
    expect(graded.stage).toBe("evaluation");
    expect(graded.quiz).toMatchObject({ submitted: true, answers });
    expect(graded.evaluation).toMatchObject({ correct: 2, total: 3 });
    expect(graded.evaluation?.perQuestion[0]).toMatchObject({
      correctIndex: 1,
      isCorrect: true,
      explanation: `${SECRET_EXPLANATION}-1`,
    });
    expect(graded.score?.tier).toBe("Practitioner");

    // The Supervisor ran once, after grading, with the evaluate call in its
    // history, so it can write the summary.
    expect(runSupervisor).toHaveBeenCalledTimes(1);
    const messages = runSupervisor.mock.calls[0]?.[0] ?? [];
    expect(messages.map(({ role }) => role)).toEqual(["assistant", "tool"]);
  });
});
