import type { KeyTerm } from "@repo/shared/schemas";
import { Layers } from "lucide-react";

import { CARD_CLASS } from "@/features/canvas/constants/canvas";

export interface FlashcardsViewProps {
  title: string;
  /** The card on screen; `null` when there are no key terms. */
  card: KeyTerm | null;
  /** 1-based position of the card. */
  position: number;
  count: number;
  isFlipped: boolean;
  hasPrev: boolean;
  hasNext: boolean;
  onFlip: () => void;
  onPrev: () => void;
  onNext: () => void;
}

/** One flip card at a time: the term on the front, its definition behind. */
export const FlashcardsView = ({
  title,
  card,
  position,
  count,
  isFlipped,
  hasPrev,
  hasNext,
  onFlip,
  onPrev,
  onNext,
}: FlashcardsViewProps) => (
  <section className={CARD_CLASS}>
    <div className="mb-4 flex items-center justify-between">
      <h4 className="flex items-center gap-2 text-sm font-bold">
        <Layers className="h-4 w-4 text-indigo-500" /> {title}
        {card && (
          <span className="font-normal text-slate-400">
            ({position}/{count})
          </span>
        )}
      </h4>
      {card && (
        <span className="text-xs text-slate-400">Click card to flip</span>
      )}
    </div>

    {card ? (
      <>
        <button
          type="button"
          onClick={onFlip}
          aria-pressed={isFlipped}
          aria-label={
            isFlipped
              ? `Definition of ${card.term}`
              : `Show definition of ${card.term}`
          }
          className={`flex h-44 w-full flex-col items-center justify-center rounded-xl border-2 border-dashed p-6 text-center transition-all duration-300 select-none focus:outline-none focus-visible:ring-4 focus-visible:ring-indigo-300 ${
            isFlipped
              ? "scale-[0.99] border-indigo-500 bg-indigo-600 text-white"
              : "border-slate-300 bg-slate-50 hover:border-indigo-400 dark:border-slate-700 dark:bg-slate-900 dark:hover:border-indigo-500"
          }`}
        >
          {isFlipped ? (
            <>
              <span className="text-xs font-semibold tracking-wider text-indigo-200 uppercase">
                Definition
              </span>
              <span className="mt-2 text-sm leading-relaxed font-medium">
                {card.definition}
              </span>
            </>
          ) : (
            <>
              <span className="text-xs font-semibold tracking-wider text-indigo-500 uppercase">
                Concept
              </span>
              <span className="mt-1 text-xl font-bold">{card.term}</span>
              <span className="mt-4 text-[11px] text-slate-400">
                Click to reveal the definition
              </span>
            </>
          )}
        </button>

        <div className="mt-4 flex items-center justify-between">
          <button
            type="button"
            onClick={onPrev}
            disabled={!hasPrev}
            className="rounded-lg border border-slate-200 px-3 py-1.5 text-xs font-medium disabled:opacity-40 dark:border-slate-700"
          >
            Previous Card
          </button>
          <button
            type="button"
            onClick={onNext}
            disabled={!hasNext}
            className="rounded-lg bg-indigo-600 px-3 py-1.5 text-xs font-medium text-white disabled:opacity-40"
          >
            Next Card
          </button>
        </div>
      </>
    ) : (
      <p className="text-xs text-slate-500 dark:text-slate-400">
        No key terms in this research.
      </p>
    )}
  </section>
);
