import { createMiddleware } from "langchain";

import {
  SUMMARY_KEEP_TURNS,
  SUMMARY_TRIGGER_TOKENS,
} from "../../constants/memory";
import {
  LearningGraphStateSchema,
  RunContextSchema,
} from "../../schemas/graph";
import { planSummary } from "../../utils/conversation-summary";
import { summarizeConversation } from "../memory/summarize-conversation";

/**
 * Short-term memory (E1b). After each turn, once the messages the summary
 * does not cover pass `SUMMARY_TRIGGER_TOKENS`, the older ones are folded
 * into `summary` and `summarizedUpTo` moves past them. The last
 * `SUMMARY_KEEP_TURNS` turns stay verbatim, a tool call is never cut from
 * its result, and `messages` is never changed: the Supervisor's context
 * (`supervisorContextMiddleware`) is what leaves the folded ones out.
 *
 * A failed summary is logged and tried again after the next turn; a
 * stopped run saves nothing.
 */
export const createConversationSummaryMiddleware = (apiKey: string) =>
  createMiddleware({
    name: "ConversationSummary",
    stateSchema: LearningGraphStateSchema,
    contextSchema: RunContextSchema,
    afterAgent: async (state, runtime) => {
      const plan = planSummary(state.messages, state.summarizedUpTo, {
        triggerTokens: SUMMARY_TRIGGER_TOKENS,
        keepTurns: SUMMARY_KEEP_TURNS,
      });
      if (!plan) {
        return undefined;
      }

      try {
        const summary = await summarizeConversation({
          settings: { ...runtime.context.settings, apiKey },
          previous: state.summary,
          messages: plan.fold,
          signal: runtime.signal,
        });
        return { summary, summarizedUpTo: plan.upTo };
      } catch (error) {
        if (runtime.signal?.aborted) {
          throw error;
        }
        console.error("[summary] Folding older messages failed", error);
        return undefined;
      }
    },
  });
