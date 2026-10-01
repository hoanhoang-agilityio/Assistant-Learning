import type { LearningRecords } from "../../../types/records";

export interface RecordedCall {
  method: keyof LearningRecords;
  threadId: string;
  value: unknown;
}

/** Records that keep every call, so a test can see what a run saved. */
export const createMemoryRecords = () => {
  const calls: RecordedCall[] = [];
  const keep =
    (method: keyof LearningRecords) =>
    async (threadId: string, value: unknown) => {
      calls.push({ method, threadId, value });
    };

  const records: LearningRecords = {
    recordRun: keep("recordRun"),
    recordResearch: keep("recordResearch"),
    recordMaterial: keep("recordMaterial"),
    recordQuiz: keep("recordQuiz"),
    recordEvaluation: keep("recordEvaluation"),
  };
  return { records, calls };
};
