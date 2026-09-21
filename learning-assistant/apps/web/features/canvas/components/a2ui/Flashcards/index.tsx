import type { KeyTerm } from "@repo/shared/schemas";

import { FlashcardsView } from "@/features/canvas/components/a2ui/FlashcardsView";
import { useFlashcards } from "@/features/canvas/hooks/use-flashcards";
import type { CanvasComponentProps } from "@/features/canvas/types/a2ui";
import { readList, readText } from "@/features/canvas/utils/a2ui-props";

/** Key-term flip cards, bound to the research's key terms. */
export const Flashcards = ({ props }: CanvasComponentProps<"Flashcards">) => {
  const cards = readList<KeyTerm>(props.cards);
  const {
    index,
    isFlipped,
    hasPrev,
    hasNext,
    handleFlip,
    handlePrev,
    handleNext,
  } = useFlashcards(cards.length);

  return (
    <FlashcardsView
      title={readText(props.title)}
      card={cards[index] ?? null}
      position={index + 1}
      count={cards.length}
      isFlipped={isFlipped}
      hasPrev={hasPrev}
      hasNext={hasNext}
      onFlip={handleFlip}
      onPrev={handlePrev}
      onNext={handleNext}
    />
  );
};
