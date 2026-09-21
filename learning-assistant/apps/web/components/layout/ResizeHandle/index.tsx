"use client";

import type { RefObject } from "react";

import { ResizeHandleView } from "@/components/layout/ResizeHandleView";
import { useChatResize } from "@/hooks/use-chat-resize";

export interface ResizeHandleProps {
  /** The row holding the chat and the canvas; widths are measured from it. */
  containerRef: RefObject<HTMLDivElement | null>;
}

/** The chat divider, wired to drag and keyboard resizing. */
export const ResizeHandle = ({ containerRef }: ResizeHandleProps) => {
  const {
    chatWidth,
    isDragging,
    handlePointerDown,
    handlePointerMove,
    handlePointerEnd,
    handleKeyDown,
    handleReset,
  } = useChatResize(containerRef);

  return (
    <ResizeHandleView
      width={chatWidth}
      isDragging={isDragging}
      onPointerDown={handlePointerDown}
      onPointerMove={handlePointerMove}
      onPointerEnd={handlePointerEnd}
      onKeyDown={handleKeyDown}
      onReset={handleReset}
    />
  );
};
