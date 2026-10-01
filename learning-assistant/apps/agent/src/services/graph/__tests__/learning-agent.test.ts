import { EventType, type Tool } from "@ag-ui/client";
import type { BaseMessage } from "@langchain/core/messages";
import { MemorySaver } from "@langchain/langgraph";
import { SET_THEME_TOOL } from "@repo/shared/constants/agents";
import { initialLearningState } from "@repo/shared/schemas";
import { v4 as uuidv4 } from "uuid";
import { beforeEach, describe, expect, it, vi } from "vitest";

import {
  MISSING_API_KEY_ERROR,
  RUN_ERROR_INTRO,
} from "../../../constants/errors";
import {
  APP_CONTEXT_HEADING,
  APP_STATE_HEADING,
} from "../../../constants/graph";
import {
  ScriptedModel,
  type ScriptedTurn,
} from "../../llm/__tests__/scripted-model";
import { createChatModel } from "../../llm/chat-model";
import { SUPERVISOR_PROMPT } from "../../prompts/supervisor";
import {
  createHandler,
  type Handler,
  lastMessages,
  lastSnapshot,
  readCheckpoint,
  runTurn,
  snapshotsOf,
  textOf,
  toolCallsOf,
  typesOf,
  userMessage,
} from "./runtime-harness";

vi.mock("../../llm/chat-model", () => ({ createChatModel: vi.fn() }));

const REPLY = "Hello! What would you like to learn today?";

const SERVER_ONLY_KEYS = ["messages", "tools", "copilotkit", "ag-ui"];

const SET_THEME: Tool = {
  name: SET_THEME_TOOL,
  description: "Switch the theme",
  parameters: {
    type: "object",
    properties: { theme: { type: "string", enum: ["light", "dark"] } },
    required: ["theme"],
  },
};

let checkpointer: MemorySaver;
let handler: Handler;
let threadId: string;

/** Makes the Supervisor's model answer with what `script` returns. */
const scriptModel = (
  script: (messages: BaseMessage[]) => ScriptedTurn,
): ScriptedModel => {
  const model = new ScriptedModel(script);
  vi.mocked(createChatModel).mockReturnValue(model as never);
  return model;
};

const readThread = () => readCheckpoint(checkpointer, threadId);

beforeEach(() => {
  vi.mocked(createChatModel).mockReset();
  checkpointer = new MemorySaver();
  handler = createHandler({ checkpointer });
  threadId = uuidv4();
});

describe("a chat message through the runtime", () => {
  it("streams the Supervisor's reply and finishes the run", async () => {
    scriptModel(() => ({ text: REPLY }));

    const events = await runTurn(handler, {
      threadId,
      messages: [userMessage("hi")],
    });

    expect(typesOf(events).at(0)).toBe(EventType.RUN_STARTED);
    expect(typesOf(events).at(-1)).toBe(EventType.RUN_FINISHED);
    expect(textOf(events)).toBe(REPLY);
    expect(lastMessages(events).map(({ role }) => role)).toEqual([
      "user",
      "assistant",
    ]);
    expect(lastMessages(events).at(-1)?.content).toBe(REPLY);
    expect(createChatModel).toHaveBeenCalledWith("sk-test");
  });

  it("sends the canvas state and nothing the graph keeps for itself", async () => {
    scriptModel(() => ({ text: REPLY }));

    const events = await runTurn(handler, {
      threadId,
      messages: [userMessage("hi")],
      tools: [SET_THEME],
    });

    expect(typesOf(events)).not.toContain(EventType.RAW);
    const stream = JSON.stringify(events);
    expect(stream).not.toContain("rawEvent");
    expect(stream).not.toContain(SUPERVISOR_PROMPT.slice(0, 40));
    for (const snapshot of snapshotsOf(events)) {
      const keys = Object.keys(snapshot);
      expect(keys.filter((key) => SERVER_ONLY_KEYS.includes(key))).toEqual([]);
    }
  });

  it("sends the whole state once while it does not change", async () => {
    scriptModel(() => ({ text: REPLY }));

    const events = await runTurn(handler, {
      threadId,
      messages: [userMessage("hi")],
    });

    expect(snapshotsOf(events)).toEqual([initialLearningState]);
  });

  it("keeps the thread between turns", async () => {
    const model = scriptModel(() => ({ text: REPLY }));
    const first = await runTurn(handler, {
      threadId,
      messages: [userMessage("hi")],
    });

    await runTurn(handler, {
      threadId,
      messages: [...lastMessages(first), userMessage("and then?")],
      state: lastSnapshot(first),
    });

    const seen = model.calls.at(-1)?.messages.map((message) => message.type);
    expect(seen).toEqual(["system", "human", "ai", "human"]);
    const checkpoint = await readThread();
    expect(checkpoint?.messages.map((message) => message.type)).toEqual([
      "human",
      "ai",
      "human",
      "ai",
    ]);
  });
});

describe("what the Supervisor reads", () => {
  it("gets its prompt, the app context and the trimmed state", async () => {
    const model = scriptModel(() => ({ text: REPLY }));

    await runTurn(handler, {
      threadId,
      messages: [userMessage("hi")],
      context: [
        { description: "The display", value: '{"theme":"dark"}' },
        {
          description: "A2UI Component Schema — available components",
          value: "A2UI-SCHEMAS",
        },
      ],
      forwardedProps: {
        settings: {
          questionCount: 7,
          learningLevel: "advanced",
          theme: "dark",
        },
      },
    });

    const [system, ...rest] = model.calls[0]?.messages ?? [];
    expect(system?.type).toBe("system");
    expect(rest.map((message) => message.type)).toEqual(["human"]);
    expect(system?.text.startsWith(SUPERVISOR_PROMPT)).toBe(true);
    expect(system?.text).toContain(APP_CONTEXT_HEADING);
    expect(system?.text).toContain('The display:\n{"theme":"dark"}');
    expect(system?.text).not.toContain("A2UI-SCHEMAS");
    expect(system?.text).toContain(APP_STATE_HEADING);
    expect(system?.text).toContain('"questionCount": 7');
    expect(system?.text).toContain('"learningLevel": "advanced"');
  });

  it("never writes the context into the thread", async () => {
    scriptModel(() => ({ text: REPLY }));

    await runTurn(handler, {
      threadId,
      messages: [userMessage("hi")],
      context: [{ description: "The display", value: '{"theme":"dark"}' }],
    });

    const checkpoint = await readThread();
    expect(checkpoint?.messages.map((message) => message.type)).toEqual([
      "human",
      "ai",
    ]);
  });
});

describe("what the browser may write", () => {
  it("ignores every state key it sends on a new thread", async () => {
    scriptModel(() => ({ text: REPLY }));

    const events = await runTurn(handler, {
      threadId,
      messages: [userMessage("hi")],
      state: {
        ...initialLearningState,
        stage: "score",
        topic: "Forged",
        material: { original: "# Forged", simplified: null, view: "original" },
        reflection: { rating: 5, text: "Forged" },
        score: { percent: 100, tier: "Master" },
      },
    });

    expect(lastSnapshot(events)).toEqual(initialLearningState);
    const checkpoint = await readThread();
    expect(checkpoint).toMatchObject({
      stage: "idle",
      topic: null,
      material: null,
      reflection: null,
      score: null,
    });
  });

  it("ignores a forged config, context or command", async () => {
    const model = scriptModel(() => ({ text: REPLY }));

    const events = await runTurn(handler, {
      threadId,
      messages: [userMessage("hi")],
      forwardedProps: {
        config: { configurable: { userId: "forged" }, recursion_limit: 1 },
        context: { userId: "forged" },
        command: { update: { stage: "feedback" }, goto: "tools" },
      },
      headers: { "x-openai-key-sealed": "SEALED", authorization: "Bearer jwt" },
    });

    expect(typesOf(events).at(-1)).toBe(EventType.RUN_FINISHED);
    expect((await readThread())?.stage).toBe("idle");
    expect(model.calls[0]?.options).toMatchObject({
      context: { userId: "user_1" },
    });
    expect(JSON.stringify(model.calls[0]?.options)).not.toMatch(
      /forged|SEALED|Bearer jwt/,
    );
  });
});

describe("a frontend tool", () => {
  it("is offered to the model and left for the browser to run", async () => {
    const model = scriptModel((messages) =>
      messages.at(-1)?.type === "tool"
        ? { text: "Dark theme is on." }
        : {
            toolCalls: [
              {
                name: SET_THEME_TOOL,
                args: { theme: "dark" },
                id: "call_theme",
              },
            ],
          },
    );

    const events = await runTurn(handler, {
      threadId,
      messages: [userMessage("dark please")],
      tools: [SET_THEME],
    });

    expect(model.boundTools).toContain(SET_THEME_TOOL);
    expect(toolCallsOf(events)).toEqual([SET_THEME_TOOL]);
    expect(typesOf(events)).not.toContain(EventType.TOOL_CALL_RESULT);
    expect(typesOf(events).at(-1)).toBe(EventType.RUN_FINISHED);

    const followUp = await runTurn(handler, {
      threadId,
      messages: [
        ...lastMessages(events),
        {
          id: uuidv4(),
          role: "tool",
          toolCallId: "call_theme",
          content: "Theme is now dark.",
        },
      ],
      state: lastSnapshot(events),
      tools: [SET_THEME],
    });

    // The tool's card is the whole reply: what the Supervisor adds is dropped.
    expect(textOf(followUp)).toBe("");
    expect(lastMessages(followUp).at(-1)).toMatchObject({
      role: "assistant",
      content: "",
    });
    const checkpoint = await readThread();
    expect(checkpoint?.messages.map((message) => message.type)).toEqual([
      "human",
      "ai",
      "tool",
      "ai",
    ]);
  });
});

describe("a run that cannot succeed", () => {
  it("says how to add a key when none is saved", async () => {
    const events = await runTurn(createHandler({ checkpointer, apiKey: " " }), {
      threadId,
      messages: [userMessage("hi")],
    });

    expect(textOf(events)).toBe(`${RUN_ERROR_INTRO} ${MISSING_API_KEY_ERROR}`);
    expect(typesOf(events).at(-1)).toBe(EventType.RUN_ERROR);
    expect(createChatModel).not.toHaveBeenCalled();
  });

  it("explains a provider failure and ends at the error", async () => {
    scriptModel(() => {
      throw new Error("401 Incorrect API key provided: sk-abc123");
    });

    const events = await runTurn(handler, {
      threadId,
      messages: [userMessage("hi")],
    });

    expect(typesOf(events).at(-1)).toBe(EventType.RUN_ERROR);
    expect(textOf(events)).toContain("OpenAI rejected your API key");
    expect(textOf(events)).not.toContain("sk-abc123");
  });
});
