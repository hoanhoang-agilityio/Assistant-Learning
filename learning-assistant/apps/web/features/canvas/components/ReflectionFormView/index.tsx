import { CheckCircle2, MessageCircle, Pencil } from "lucide-react";
import type { FormEvent } from "react";

import { CARD_CLASS } from "@/features/canvas/constants/canvas";
import {
  RATING_LABEL_ID,
  RATING_OPTIONS,
  RATING_STAR,
} from "@/features/canvas/constants/feedback";

export interface ReflectionFormViewProps {
  /** 0 until a star is picked. */
  rating: number;
  text: string;
  isSaved: boolean;
  canSubmit: boolean;
  /** The agent is running; saving waits for it. */
  isLocked: boolean;
  onRatingChange: (rating: number) => void;
  onTextChange: (text: string) => void;
  onSubmit: () => void;
  onEdit: () => void;
}

/** Star rating and takeaways, or a confirmation once they are saved. */
export const ReflectionFormView = ({
  rating,
  text,
  isSaved,
  canSubmit,
  isLocked,
  onRatingChange,
  onTextChange,
  onSubmit,
  onEdit,
}: ReflectionFormViewProps) => {
  const handleSubmit = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    onSubmit();
  };

  return (
    <section className={CARD_CLASS}>
      <h3 className="mb-2 flex items-center gap-2 text-base font-bold">
        <MessageCircle className="h-5 w-5 text-indigo-500" /> Session Reflection
      </h3>
      <p className="mb-6 text-xs text-slate-400">
        Tell your assistant how this lesson went; it reads your reflection in
        the chat.
      </p>

      {isSaved ? (
        <div className="space-y-2 rounded-xl border border-emerald-500/20 bg-emerald-500/10 p-6 text-center">
          <CheckCircle2 className="mx-auto h-8 w-8 text-emerald-500" />
          <h4 className="text-sm font-bold text-emerald-600 dark:text-emerald-400">
            Reflection saved
          </h4>
          <p className="text-xs break-words text-slate-500 dark:text-slate-400">
            <span className="text-amber-500">{RATING_STAR.repeat(rating)}</span>
            {text && ` — ${text}`}
          </p>
          <button
            type="button"
            disabled={isLocked}
            onClick={onEdit}
            className="mx-auto mt-2 flex items-center gap-1 rounded-lg px-2.5 py-1 text-xs font-medium text-emerald-700 hover:bg-emerald-500/10 disabled:opacity-40 dark:text-emerald-300"
          >
            <Pencil className="h-3 w-3" /> Edit reflection
          </button>
        </div>
      ) : (
        <form onSubmit={handleSubmit} className="space-y-4">
          <div>
            <p id={RATING_LABEL_ID} className="mb-2 text-xs font-medium">
              How satisfied were you with this lesson?
            </p>
            <div
              role="radiogroup"
              aria-labelledby={RATING_LABEL_ID}
              className="flex gap-2"
            >
              {RATING_OPTIONS.map((star) => (
                <button
                  key={star}
                  type="button"
                  role="radio"
                  aria-checked={rating === star}
                  aria-label={`${star} of ${RATING_OPTIONS.length}`}
                  onClick={() => onRatingChange(star)}
                  className={`h-10 w-10 rounded-xl border text-sm font-bold transition-all ${
                    rating >= star
                      ? "border-amber-400 bg-amber-400 text-slate-900 shadow-sm"
                      : "border-slate-200 hover:bg-slate-100 dark:border-slate-700 dark:hover:bg-slate-700"
                  }`}
                >
                  {RATING_STAR}
                </button>
              ))}
            </div>
          </div>

          <label className="block">
            <span className="mb-1 block text-xs font-medium">
              Key takeaways or topics to review next time:
            </span>
            <textarea
              value={text}
              onChange={(event) => onTextChange(event.target.value)}
              rows={4}
              placeholder="e.g. I want more examples on my weakest concept next time…"
              className="w-full rounded-xl border border-slate-200 bg-slate-50 p-3 text-xs text-slate-800 outline-none focus:border-indigo-500 dark:border-slate-700 dark:bg-slate-900 dark:text-slate-200"
            />
          </label>

          <div className="flex flex-wrap items-center gap-3">
            <button
              type="submit"
              disabled={!canSubmit}
              className="rounded-xl bg-indigo-600 px-5 py-2.5 text-xs font-semibold text-white shadow-md shadow-indigo-600/20 hover:bg-indigo-700 disabled:cursor-not-allowed disabled:opacity-40 disabled:hover:bg-indigo-600"
            >
              Save reflection &amp; send to chat
            </button>
            <span className="text-[11px] text-slate-400" aria-live="polite">
              {isLocked
                ? "The assistant is working — you can save when it is done."
                : rating === 0 && "Pick a rating to save."}
            </span>
          </div>
        </form>
      )}
    </section>
  );
};
