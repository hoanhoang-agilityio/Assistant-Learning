import type { LearningRecords } from "@repo/agent";
import {
  getDatabase,
  recordConversationRun,
  recordEvaluation,
  recordMaterial,
  recordQuiz,
  recordResearch,
} from "@repo/db";

/**
 * Where the agent keeps each conversation's runs and completed stages: the
 * domain tables. The agent only calls these after the thread guard has
 * checked the conversation is the caller's.
 */
export const conversationRecords: LearningRecords = {
  recordRun: (threadId, run) =>
    recordConversationRun(getDatabase(), threadId, run),
  recordResearch: (threadId, record) =>
    recordResearch(getDatabase(), threadId, record),
  recordMaterial: (threadId, material) =>
    recordMaterial(getDatabase(), threadId, material),
  recordQuiz: (threadId, quiz) => recordQuiz(getDatabase(), threadId, quiz),
  recordEvaluation: (threadId, record) =>
    recordEvaluation(getDatabase(), threadId, record),
};
