import type { LearningRecords } from "../../types/records";

const skip = async () => {};

/** Keeps nothing: for a graph that only reads checkpoints. */
export const NO_RECORDS: LearningRecords = {
  recordRun: skip,
  recordResearch: skip,
  recordMaterial: skip,
  recordQuiz: skip,
  recordEvaluation: skip,
};
