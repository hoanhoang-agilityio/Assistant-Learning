import { useState } from "react";

/**
 * Which card is showing and whether it is flipped. Local to the component:
 * flipping is not part of the agent's state.
 */
export const useFlashcards = (count: number) => {
  const [index, setIndex] = useState(0);
  const [isFlipped, setIsFlipped] = useState(false);
  // New research can bring fewer cards; stay on a card that exists.
  const current = Math.min(index, Math.max(count - 1, 0));

  const handleMove = (next: number) => {
    setIndex(next);
    setIsFlipped(false);
  };

  return {
    index: current,
    isFlipped,
    hasPrev: current > 0,
    hasNext: current < count - 1,
    handleFlip: () => setIsFlipped((flipped) => !flipped),
    handlePrev: () => handleMove(current - 1),
    handleNext: () => handleMove(current + 1),
  };
};
