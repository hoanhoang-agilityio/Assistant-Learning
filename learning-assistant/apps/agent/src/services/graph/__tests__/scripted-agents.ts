import type { BaseMessage } from "@langchain/core/messages";
import type { FeedbackComponent, QuizDraft } from "@repo/shared/schemas";
import { vi } from "vitest";

import {
  type ScriptedCall,
  ScriptedModel,
  type ScriptedTurn,
} from "../../llm/__tests__/scripted-model";
import { createChatModel } from "../../llm/chat-model";

/** Text that must never reach the client before the quiz is submitted. */
export const SECRET_EXPLANATION = "SECRET-EXPLANATION";

export const RESEARCH = {
  title: "JavaScript closures",
  summary: "A closure is a function together with the variables it captured.",
  keyInsight: "Functions remember the scope they were created in.",
  keyTerms: [{ term: "Scope", definition: "Where a name is visible." }],
};

export const MATERIAL = {
  markdown: "# Closures\nA function remembers its scope.",
};

export const SIMPLIFIED = {
  markdown: "# Closures, simply\nFunctions remember.",
};

export const QUIZ_DRAFT: QuizDraft = {
  questions: [0, 1, 2].map((index) => ({
    concept: index === 2 ? "Scope" : "Closures",
    question: `Question ${index + 1}?`,
    options: ["a", "b", "c", "d"],
    correctIndex: index + 1,
    explanation: `${SECRET_EXPLANATION}-${index + 1}`,
  })),
};

export const EXPLANATIONS = {
  explanations: [1, 2, 3].map((number) => ({
    qid: `q${number}`,
    explanation: `Explained ${number}.`,
  })),
  summary: "Solid on closures; review scope.",
};

export const SUMMARY = "The student asked about closures and got answers.";

export const FEEDBACK_COMPONENTS: FeedbackComponent[] = [
  {
    id: "root",
    component: "FeedbackCard",
    title: "Nice start",
    body: "Keep going.",
    children: ["steps"],
  },
  {
    id: "steps",
    component: "NextStepList",
    title: "Next steps",
    steps: ["Re-read Scope"],
  },
];

/** What each subagent's model writes; an `Error` makes that call fail. */
interface SubagentReplies {
  research: object | Error;
  material: object | Error;
  quiz: object | Error;
  explanations: object | Error;
  feedback: FeedbackComponent[] | Error;
  /** The summariser's summary of a conversation's older messages. */
  summary: object | Error;
  /** How long the Research Agent's model takes to start answering. */
  researchDelayMs?: number;
}

const DEFAULT_REPLIES: SubagentReplies = {
  research: RESEARCH,
  material: MATERIAL,
  quiz: QUIZ_DRAFT,
  explanations: EXPLANATIONS,
  feedback: FEEDBACK_COMPONENTS,
  summary: { summary: SUMMARY },
};

const toJsonTurn = (reply: object | Error, delayMs?: number): ScriptedTurn => {
  if (reply instanceof Error) {
    throw reply;
  }
  return { text: JSON.stringify(reply), delayMs };
};

/** The JSON schema properties a structured-output call asked for. */
const readSchemaKeys = ({ options }: ScriptedCall): string[] => {
  const { response_format: format } = options as {
    response_format?: {
      json_schema?: { schema?: { properties?: Record<string, unknown> } };
    };
  };
  return Object.keys(format?.json_schema?.schema?.properties ?? {});
};

/**
 * Scripts every model of a run. `supervisor` answers the Supervisor's calls;
 * each subagent and memory call is recognised by the output it asks for and
 * answered from `replies`. Returns the Supervisor's calls and the
 * summariser's, each in order, and every model that was created (the first
 * is the Supervisor's).
 */
export const scriptAgents = (
  supervisor: (messages: BaseMessage[], call: ScriptedCall) => ScriptedTurn,
  replies: Partial<SubagentReplies> = {},
) => {
  const all = { ...DEFAULT_REPLIES, ...replies };
  const supervisorCalls: ScriptedCall[] = [];
  const summaryCalls: ScriptedCall[] = [];

  const script = (
    messages: BaseMessage[],
    call: ScriptedCall,
  ): ScriptedTurn => {
    if (call.tools.includes("render_a2ui")) {
      if (all.feedback instanceof Error) {
        throw all.feedback;
      }
      return {
        toolCalls: [
          {
            name: "render_a2ui",
            args: { surfaceId: "any", components: all.feedback },
          },
        ],
      };
    }

    const keys = readSchemaKeys(call);
    if (keys.includes("keyInsight")) {
      return toJsonTurn(all.research, all.researchDelayMs);
    }
    if (keys.includes("markdown")) {
      return toJsonTurn(all.material);
    }
    if (keys.includes("questions")) {
      return toJsonTurn(all.quiz);
    }
    if (keys.includes("explanations")) {
      return toJsonTurn(all.explanations);
    }
    if (keys.length === 1 && keys[0] === "summary") {
      summaryCalls.push(call);
      return toJsonTurn(all.summary);
    }

    supervisorCalls.push(call);
    return supervisor(messages, call);
  };

  const models: ScriptedModel[] = [];
  vi.mocked(createChatModel).mockImplementation(() => {
    const model = new ScriptedModel(script);
    models.push(model);
    return model as never;
  });
  return { supervisorCalls, summaryCalls, models };
};

/** The text of the last message a student wrote. */
export const lastHumanText = (messages: BaseMessage[]): string =>
  messages.filter((message) => message.type === "human").at(-1)?.text ?? "";

/** Whether the model is being called right after a tool returned. */
export const isAfterTool = (messages: BaseMessage[]): boolean =>
  messages.at(-1)?.type === "tool";

const LEARNING_PATH = ["research", "makeMaterial", "generateQuiz"];

/**
 * A Supervisor that runs the whole learning path when asked to ("teach me
 * …"), one tool after another. Once the path is done, or for any other
 * message, it does what `otherwise` says (by default it only replies).
 */
export const teachThen = (
  otherwise: (
    messages: BaseMessage[],
    call: ScriptedCall,
  ) => ScriptedTurn = () => ({ text: "Done." }),
  replies: Partial<SubagentReplies> = {},
) =>
  scriptAgents((messages, call) => {
    const done = messages.filter((message) => message.type === "tool");
    const next = LEARNING_PATH[done.length];
    if (!next || !lastHumanText(messages).startsWith("teach me")) {
      return otherwise(messages, call);
    }
    return {
      toolCalls: [
        { name: next, args: next === "research" ? { topic: "closures" } : {} },
      ],
    };
  }, replies);
