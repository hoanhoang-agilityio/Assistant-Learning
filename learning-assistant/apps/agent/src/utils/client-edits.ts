import {
  type LearningState,
  MaterialSchema,
  type Quiz,
  QuizSchema,
} from "@repo/shared/schemas";
import { replaceMaterial, retakeQuiz } from "@repo/shared/utils/client-edits";
import { z } from "zod";

/**
 * The fields the browser may change in the state, read from the state it
 * sent with a run. Everything else it sent is ignored; a field that does not
 * parse counts as not sent.
 */
const ClientQuizSchema = z.object({
  id: QuizSchema.shape.id,
  answers: QuizSchema.shape.answers,
  submitted: QuizSchema.shape.submitted.optional(),
});

const readField = <T>(schema: z.ZodType<T>, raw: unknown): T | undefined => {
  const parsed = schema.safeParse(raw);
  return parsed.success ? parsed.data : undefined;
};

const isSameAnswers = (a: Quiz["answers"], b: Quiz["answers"]): boolean => {
  const ids = Object.keys(a);
  return (
    ids.length === Object.keys(b).length && ids.every((id) => a[id] === b[id])
  );
};

/**
 * The browser's learning material: its text (an edit) and its view. It
 * cannot create learning material, remove it, or add a simplified version
 * where the server has none.
 */
const applyMaterial = (state: LearningState, raw: unknown): LearningState => {
  const material = readField(MaterialSchema, raw);
  if (!material || !state.material) {
    return state;
  }
  const hasSimplified = state.material.simplified !== null;

  return replaceMaterial(state, {
    original: material.original,
    simplified: hasSimplified
      ? (material.simplified ?? state.material.simplified)
      : null,
    view: hasSimplified ? material.view : "original",
  });
};

/**
 * The browser's answers, for the quiz the server holds and its questions
 * only. The canvas locks a graded quiz, so a graded quiz the browser holds
 * as not submitted, or with other answers, means the student pressed Retake:
 * the results are cleared. The browser can undo a grade this way, never
 * make one.
 */
const applyAnswers = (state: LearningState, raw: unknown): LearningState => {
  const client = readField(ClientQuizSchema, raw);
  const { quiz } = state;
  if (!client || !quiz || client.id !== quiz.id) {
    return state;
  }

  const answers = Object.fromEntries(
    quiz.questions.flatMap(({ id }) => {
      const answer = client.answers[id];
      return answer === undefined ? [] : [[id, answer]];
    }),
  );
  const isSame = isSameAnswers(answers, quiz.answers);
  const isRetake = quiz.submitted && (client.submitted === false || !isSame);
  if (isSame && !isRetake) {
    return state;
  }

  const base = isRetake ? retakeQuiz(state) : state;
  return { ...base, quiz: { ...quiz, answers, submitted: false } };
};

/**
 * Applies what the browser changed since the last run to the server's
 * `state`: the learning material's text and view, and the quiz answers, each with what follows from it (an edit clears the quiz, a
 * retake clears the results). `client` is the state the browser sent; only
 * those fields are read, so it cannot write a stage, a quiz, a grade or
 * anything else the server owns.
 */
export const applyClientEdits = (
  state: LearningState,
  client: unknown,
): LearningState => {
  const { material, quiz } = (client ?? {}) as Record<string, unknown>;
  return applyAnswers(applyMaterial(state, material), quiz);
};
