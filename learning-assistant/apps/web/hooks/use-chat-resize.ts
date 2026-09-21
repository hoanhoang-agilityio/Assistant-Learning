import {
  type KeyboardEvent,
  type PointerEvent,
  type RefObject,
  useRef,
  useState,
} from "react";

import {
  CHAT_RESIZE_STEP,
  RESIZE_KEYS,
  RESIZING_BODY_CLASS,
} from "@/constants/layout";
import { useLayout, useLayoutActions } from "@/hooks/use-layout-store";

/**
 * Drag and keyboard resizing for the chat divider. `containerRef` is the row
 * holding the chat and the canvas; widths are measured from it.
 */
export const useChatResize = (
  containerRef: RefObject<HTMLDivElement | null>,
) => {
  const { chatWidth } = useLayout();
  const { setChatWidth, resetChatWidth } = useLayoutActions();
  // The ref gates pointer moves (a fast drag can move before a re-render);
  // the state only drives the highlight.
  const isDraggingRef = useRef(false);
  const [isDragging, setIsDragging] = useState(false);

  const resizeTo = (width: number) => {
    setChatWidth(width, containerRef.current?.getBoundingClientRect().width);
  };

  const handlePointerDown = (event: PointerEvent<HTMLDivElement>) => {
    event.preventDefault();
    event.currentTarget.setPointerCapture(event.pointerId);

    isDraggingRef.current = true;
    setIsDragging(true);
    document.body.classList.add(RESIZING_BODY_CLASS);
  };

  const handlePointerMove = (event: PointerEvent<HTMLDivElement>) => {
    if (!isDraggingRef.current) return;

    const left = containerRef.current?.getBoundingClientRect().left ?? 0;
    resizeTo(event.clientX - left);
  };

  const handlePointerEnd = (event: PointerEvent<HTMLDivElement>) => {
    if (event.currentTarget.hasPointerCapture(event.pointerId)) {
      event.currentTarget.releasePointerCapture(event.pointerId);
    }

    isDraggingRef.current = false;
    setIsDragging(false);
    document.body.classList.remove(RESIZING_BODY_CLASS);
  };

  const handleKeyDown = (event: KeyboardEvent<HTMLDivElement>) => {
    if (event.key === RESIZE_KEYS.narrower) {
      event.preventDefault();
      resizeTo(chatWidth - CHAT_RESIZE_STEP);
    } else if (event.key === RESIZE_KEYS.wider) {
      event.preventDefault();
      resizeTo(chatWidth + CHAT_RESIZE_STEP);
    } else if (event.key === RESIZE_KEYS.reset) {
      event.preventDefault();
      resetChatWidth();
    }
  };

  return {
    chatWidth,
    isDragging,
    handlePointerDown,
    handlePointerMove,
    handlePointerEnd,
    handleKeyDown,
    handleReset: resetChatWidth,
  };
};
