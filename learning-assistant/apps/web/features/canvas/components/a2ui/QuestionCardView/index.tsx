import { CheckCircle2, Lightbulb, XCircle } from "lucide-react";

import { CARD_CLASS } from "@/features/canvas/constants/canvas";
import {
  OPTION_LETTERS,
  QUESTION_LABEL_ID_PREFIX,
} from "@/features/canvas/constants/quiz";
import type { OptionState, QuestionResult } from "@/features/canvas/types/a2ui";
import { getOptionState } from "@/features/canvas/utils/quiz-options";

export interface QuestionCardViewProps {
  /** 1-based position in the quiz. */
  number: number;
  concept: string;
  question: string;
  options: string[];
  selectedIndex: number | null;
  /** `null` until the quiz is graded. */
  result: QuestionResult | null;
  /** Graded, or the agent is running. */
  isDisabled: boolean;
  onSelect: (optionIndex: number) => void;
}

const OPTION_CLASS: Record<OptionState, string> = {
  idle: "border-slate-200 hover:border-indigo-300 hover:bg-slate-50 dark:border-slate-700 dark:hover:border-indigo-700 dark:hover:bg-slate-900",
  selected:
    "border-indigo-500 bg-indigo-50 text-indigo-900 dark:border-indigo-400 dark:bg-indigo-950/50 dark:text-indigo-100",
  correct:
    "border-emerald-500 bg-emerald-50 text-emerald-900 dark:border-emerald-400 dark:bg-emerald-950/40 dark:text-emerald-100",
  incorrect:
    "border-rose-500 bg-rose-50 text-rose-900 dark:border-rose-400 dark:bg-rose-950/40 dark:text-rose-100",
};

const LETTER_CLASS: Record<OptionState, string> = {
  idle: "bg-slate-100 text-slate-500 dark:bg-slate-700 dark:text-slate-300",
  selected: "bg-indigo-600 text-white",
  correct: "bg-emerald-600 text-white",
  incorrect: "bg-rose-600 text-white",
};

/** A question, its four options as a radio group, and the result once graded. */
export const QuestionCardView = ({
  number,
  concept,
  question,
  options,
  selectedIndex,
  result,
  isDisabled,
  onSelect,
}: QuestionCardViewProps) => {
  const labelId = `${QUESTION_LABEL_ID_PREFIX}${number}`;

  return (
    <section className={CARD_CLASS}>
      <div className="mb-3 flex flex-wrap items-center justify-between gap-2">
        <span className="text-xs font-semibold tracking-wider text-indigo-500 uppercase">
          Question {number}
        </span>
        <div className="flex items-center gap-2">
          {concept && (
            <span className="rounded-full bg-slate-100 px-2.5 py-0.5 text-[11px] font-medium text-slate-600 dark:bg-slate-700 dark:text-slate-300">
              {concept}
            </span>
          )}
          {result &&
            (result.isCorrect ? (
              <span className="flex items-center gap-1 text-xs font-semibold text-emerald-600 dark:text-emerald-400">
                <CheckCircle2 className="h-4 w-4" /> Correct
              </span>
            ) : (
              <span className="flex items-center gap-1 text-xs font-semibold text-rose-600 dark:text-rose-400">
                <XCircle className="h-4 w-4" /> Incorrect
              </span>
            ))}
        </div>
      </div>

      <h4 id={labelId} className="mb-4 text-sm font-bold">
        {question}
      </h4>

      <div role="radiogroup" aria-labelledby={labelId} className="space-y-2">
        {options.map((option, index) => {
          const state = getOptionState(index, selectedIndex, result);
          return (
            <button
              key={index}
              type="button"
              role="radio"
              aria-checked={index === selectedIndex}
              disabled={isDisabled}
              onClick={() => onSelect(index)}
              className={`flex w-full items-center gap-3 rounded-xl border px-4 py-3 text-left text-xs transition-colors disabled:cursor-default ${OPTION_CLASS[state]}`}
            >
              <span
                className={`flex h-6 w-6 shrink-0 items-center justify-center rounded-full text-[11px] font-bold ${LETTER_CLASS[state]}`}
              >
                {OPTION_LETTERS[index]}
              </span>
              <span className="leading-relaxed">{option}</span>
            </button>
          );
        })}
      </div>

      {result?.explanation && (
        <div className="mt-4 flex items-start gap-3 rounded-xl border border-indigo-100 bg-indigo-50/50 p-4 text-xs text-indigo-900 dark:border-indigo-900/50 dark:bg-indigo-950/30 dark:text-indigo-200">
          <Lightbulb className="mt-0.5 h-4 w-4 shrink-0 text-indigo-500" />
          <p>{result.explanation}</p>
        </div>
      )}
    </section>
  );
};
