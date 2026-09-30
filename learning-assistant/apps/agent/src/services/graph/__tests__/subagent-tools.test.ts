import { EventType } from "@ag-ui/client";
import { MemorySaver } from "@langchain/langgraph";
import { initialLearningState } from "@repo/shared/schemas";
import { v4 as uuidv4 } from "uuid";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { SUPERVISOR_MAX_STEPS } from "../../../constants/agents";
import { TOOL_ERRORS } from "../../../constants/tools";
import { createChatModel } from "../../llm/chat-model";
import {
  createHandler,
  type Handler,
  lastMessages,
  lastSnapshot,
  readCheckpoint,
  runTurn,
  snapshotsOf,
  stop,
  textOf,
  toolCallsOf,
  toolResultsOf,
  typesOf,
  userMessage,
} from "./runtime-harness";
import {
  isAfterTool,
  lastHumanText,
  MATERIAL,
  RESEARCH,
  scriptAgents,
  SECRET_EXPLANATION,
  SIMPLIFIED,
} from "./scripted-agents";

vi.mock("../../llm/chat-model", () => ({ createChatModel: vi.fn() }));

/** Every quiz in these tests has three questions. */
const SETTINGS = { questionCount: 3, learningLevel: "beginner", theme: "dark" };

/** Anything that would reveal the quiz's answer key. */
const LEAKS = ["correctIndex", "explanation", SECRET_EXPLANATION];

let checkpointer: MemorySaver;
let handler: Handler;
let threadId: string;

/** One turn in the thread under test, with the settings above. */
const send = (
  content: string,
  previous: Awaited<ReturnType<typeof runTurn>> = [],
) =>
  runTurn(handler, {
    threadId,
    messages: [...lastMessages(previous), userMessage(content)],
    state: lastSnapshot(previous),
    forwardedProps: { settings: SETTINGS },
  });

/**
 * A Supervisor that calls the tool named first in the student's message
 * ("research closures" calls `research`), then says "Done." once it returns.
 */
const callNamedTool = () =>
  scriptAgents((messages) => {
    if (isAfterTool(messages)) {
      return { text: "Done." };
    }
    const [name = "", ...rest] = lastHumanText(messages).split(" ");
    const args =
      name === "research"
        ? { topic: rest.join(" ") }
        : name === "simplify"
          ? { scope: "all" }
          : {};
    return { toolCalls: [{ name, args }] };
  });

beforeEach(() => {
  vi.mocked(createChatModel).mockReset();
  vi.stubEnv("QUIZ_SEAL_SECRET", "test-secret");
  vi.stubEnv("TAVILY_API_KEY", "");
  checkpointer = new MemorySaver();
  handler = createHandler({ checkpointer });
  threadId = uuidv4();
});

describe("research", () => {
  it("writes the research to state and moves the canvas to it", async () => {
    callNamedTool();

    const events = await send("research closures");

    expect(toolCallsOf(events)).toEqual(["research"]);
    expect(lastSnapshot(events)).toEqual({
      ...initialLearningState,
      stage: "research",
      topic: "closures",
      research: { ...RESEARCH, sources: [] },
    });
    expect(await readCheckpoint(checkpointer, threadId)).toMatchObject({
      stage: "research",
      research: { title: RESEARCH.title },
      status: { running: null },
      draft: null,
    });
  });

  it("shows the task running, then its draft, before the result", async () => {
    callNamedTool();

    const snapshots = snapshotsOf(await send("research closures"));

    const running = snapshots.findIndex(
      ({ status, draft }) =>
        (status as { running: string }).running === "research" &&
        draft === null,
    );
    const drafted = snapshots.findIndex(
      ({ draft }) => (draft as { task?: string } | null)?.task === "research",
    );
    expect(running).toBeGreaterThanOrEqual(0);
    expect(drafted).toBeGreaterThan(running);
    expect(snapshots.at(-1)).toMatchObject({
      status: { running: null },
      draft: null,
    });
    // Once the result is sent, no earlier draft comes back.
    const done = snapshots.findIndex(({ research }) => research !== null);
    expect(snapshots.slice(done).every(({ draft }) => draft === null)).toBe(
      true,
    );
  });

  it("tells the Supervisor and the card a summary, not the research", async () => {
    callNamedTool();

    const events = await send("research closures");

    expect(toolResultsOf(events)).toEqual([
      { ok: true, data: { topic: "closures", title: RESEARCH.title } },
    ]);
    const thread = await readCheckpoint(checkpointer, threadId);
    expect(JSON.stringify(thread?.messages)).not.toContain(RESEARCH.summary);
  });

  it("keeps the subagent's own tokens and the reply after the card out of the chat", async () => {
    callNamedTool();

    const events = await send("research closures");

    expect(textOf(events)).toBe("");
    expect(lastMessages(events).at(-1)).toMatchObject({
      role: "assistant",
      content: "",
    });
  });

  it("sets the error and the failed task when the subagent fails", async () => {
    scriptAgents(
      (messages) =>
        isAfterTool(messages)
          ? { text: "Research did not work." }
          : { toolCalls: [{ name: "research", args: { topic: "closures" } }] },
      { research: new Error("429 rate limit reached") },
    );

    const events = await send("research closures");

    expect(lastSnapshot(events)).toMatchObject({
      stage: "idle",
      research: null,
      draft: null,
      status: { running: null, failed: "research" },
    });
    const [result] = toolResultsOf(events) as { ok: boolean; error: string }[];
    expect(result).toMatchObject({ ok: false });
    expect(result?.error).toMatch(/^Research failed: OpenAI is rate-limiting/);
    // A failure is explained: the Supervisor's reply gets through.
    expect(textOf(events)).toBe("Research did not work.");
    expect(typesOf(events).at(-1)).toBe(EventType.RUN_FINISHED);
  });
});

describe("prerequisites", () => {
  it.each([
    ["makeMaterial", "material", TOOL_ERRORS.noResearch],
    ["simplify all", "simplify", TOOL_ERRORS.noMaterial],
    ["generateQuiz", "quiz", TOOL_ERRORS.noMaterialForQuiz],
    ["evaluate", "evaluate", TOOL_ERRORS.noQuiz],
  ])("%s fails with what is needed first", async (message, failed, error) => {
    callNamedTool();

    const events = await send(message);

    expect(toolResultsOf(events)).toEqual([{ ok: false, error }]);
    expect(lastSnapshot(events)).toMatchObject({
      stage: "idle",
      status: { running: null, error, failed },
    });
  });
});

describe("the learning path", () => {
  it("runs research, learning material and the quiz one after another", async () => {
    const { supervisorCalls } = scriptAgents((messages) => {
      const done = messages.filter((message) => message.getType() === "tool");
      const next = ["research", "makeMaterial", "generateQuiz"][done.length];
      return next
        ? {
            toolCalls: [
              {
                name: next,
                args: next === "research" ? { topic: "closures" } : {},
              },
            ],
          }
        : { text: "All set." };
    });

    const events = await send("teach me closures end to end");

    expect(toolCallsOf(events)).toEqual([
      "research",
      "makeMaterial",
      "generateQuiz",
    ]);
    expect(lastSnapshot(events)).toMatchObject({
      stage: "quiz",
      topic: "closures",
      material: {
        original: MATERIAL.markdown,
        simplified: null,
        view: "original",
      },
      quiz: { answers: {}, submitted: false },
      status: { running: null },
      draft: null,
    });
    expect(
      (lastSnapshot(events).quiz as { questions: unknown[] }).questions,
    ).toHaveLength(3);
    expect(supervisorCalls).toHaveLength(4);
    expect(textOf(events)).toBe("");
    // Each step reads the state the one before it wrote.
    const states = supervisorCalls.map(
      ({ messages }) => messages[0]?.text ?? "",
    );
    expect(states[0]).toContain('"research": null');
    expect(states[1]).toContain(`"title": "${RESEARCH.title}"`);
    expect(states[2]).toContain('"hasSimplified": false');
    expect(states[3]).toContain('"questionCount": 3,\n    "answeredCount": 0');
  });

  it("never sends or saves the quiz's answers", async () => {
    scriptAgents((messages) => {
      const done = messages.filter((message) => message.getType() === "tool");
      const next = ["research", "makeMaterial", "generateQuiz"][done.length];
      return next
        ? {
            toolCalls: [
              {
                name: next,
                args: next === "research" ? { topic: "closures" } : {},
              },
            ],
          }
        : { text: "All set." };
    });

    const events = await send("teach me closures end to end");

    const quizDrafts = snapshotsOf(events).filter(
      ({ draft }) => (draft as { task?: string } | null)?.task === "quiz",
    );
    expect(quizDrafts.length).toBeGreaterThan(0);
    const wire = JSON.stringify(events);
    const saved = JSON.stringify(await readCheckpoint(checkpointer, threadId));
    for (const leak of LEAKS) {
      expect(wire).not.toContain(leak);
      expect(saved).not.toContain(leak);
    }
    expect(saved).toContain("answerKeySealed");
  });

  it("simplifies the learning material into its own view", async () => {
    scriptAgents(
      (messages) => {
        if (isAfterTool(messages)) {
          return { text: "Done." };
        }
        const [name = ""] = lastHumanText(messages).split(" ");
        return {
          toolCalls: [
            {
              name,
              args:
                name === "research"
                  ? { topic: "closures" }
                  : name === "simplify"
                    ? { scope: "all" }
                    : {},
            },
          ],
        };
      },
      { material: MATERIAL },
    );
    const researched = await send("research closures");
    const written = await send("makeMaterial", researched);
    scriptAgents(
      (messages) =>
        isAfterTool(messages)
          ? { text: "Done." }
          : { toolCalls: [{ name: "simplify", args: { scope: "all" } }] },
      { material: SIMPLIFIED },
    );

    const events = await send("simplify all", written);

    expect(lastSnapshot(events)).toMatchObject({
      stage: "material",
      material: {
        original: MATERIAL.markdown,
        simplified: SIMPLIFIED.markdown,
        view: "simplified",
      },
    });
    expect(toolResultsOf(events)).toEqual([
      {
        ok: true,
        data: { scope: "all", characters: SIMPLIFIED.markdown.length },
      },
    ]);
  });
});

describe("Stop", () => {
  const slowResearch = () =>
    scriptAgents(
      (messages) =>
        lastHumanText(messages).startsWith("research") && !isAfterTool(messages)
          ? { toolCalls: [{ name: "research", args: { topic: "closures" } }] }
          : { text: "Hello again." },
      { researchDelayMs: 5_000 },
    );

  it("ends the run without an error and saves nothing of the step", async () => {
    slowResearch();
    const running = send("research closures");
    await new Promise((resolve) => setTimeout(resolve, 300));

    await stop(handler, threadId);
    const events = await running;

    expect(typesOf(events)).not.toContain(EventType.RUN_ERROR);
    expect(typesOf(events).at(-1)).toBe(EventType.RUN_FINISHED);
    expect(textOf(events)).toBe("");
    // The canvas showed the task running; what it ends on is what was saved.
    expect(
      snapshotsOf(events).some(
        ({ status }) => (status as { running: string }).running === "research",
      ),
    ).toBe(true);
    expect(lastSnapshot(events)).toEqual(initialLearningState);
    const thread = await readCheckpoint(checkpointer, threadId);
    expect(thread?.messages.map((message) => message.getType())).toEqual([
      "human",
      "ai",
    ]);
  });

  it("leaves a thread the next message can continue", async () => {
    const { supervisorCalls } = slowResearch();
    const running = send("research closures");
    await new Promise((resolve) => setTimeout(resolve, 300));
    await stop(handler, threadId);
    const stopped = await running;

    const events = await send("never mind, hello", stopped);

    expect(textOf(events)).toBe("Hello again.");
    expect(
      supervisorCalls.at(-1)?.messages.map((message) => message.getType()),
    ).toEqual(["system", "human", "ai", "tool", "human"]);
  });
});

describe("limits", () => {
  it("answers a tool call with bad arguments instead of failing the run", async () => {
    scriptAgents((messages) =>
      isAfterTool(messages)
        ? { text: "I sent the wrong arguments." }
        : { toolCalls: [{ name: "simplify", args: { scope: "everything" } }] },
    );

    const events = await send("simplify it");

    expect(typesOf(events)).not.toContain(EventType.RUN_ERROR);
    expect(typesOf(events).at(-1)).toBe(EventType.RUN_FINISHED);
    expect(textOf(events)).toBe("I sent the wrong arguments.");
  });

  it("asks the model for one tool call at a time", async () => {
    const { models } = callNamedTool();

    await send("research closures");

    expect(models[0]?.boundOptions).toMatchObject({
      parallel_tool_calls: false,
    });
  });

  it("ends a run that keeps calling tools", async () => {
    const { supervisorCalls } = scriptAgents(() => ({
      toolCalls: [{ name: "makeMaterial", args: {} }],
    }));

    const events = await send("loop");

    expect(supervisorCalls).toHaveLength(SUPERVISOR_MAX_STEPS);
    expect(typesOf(events).at(-1)).toBe(EventType.RUN_FINISHED);
  });
});
