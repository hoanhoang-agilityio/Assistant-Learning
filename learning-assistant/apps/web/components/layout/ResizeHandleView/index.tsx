import type { KeyboardEvent, PointerEvent } from "react";

import { CHAT_WIDTH } from "@/constants/layout";

export interface ResizeHandleViewProps {
  /** Current chat width in px. */
  width: number;
  isDragging: boolean;
  onPointerDown: (event: PointerEvent<HTMLDivElement>) => void;
  onPointerMove: (event: PointerEvent<HTMLDivElement>) => void;
  /** Pointer up or cancel. */
  onPointerEnd: (event: PointerEvent<HTMLDivElement>) => void;
  onKeyDown: (event: KeyboardEvent<HTMLDivElement>) => void;
  /** Double-click: back to the default width. */
  onReset: () => void;
}

/**
 * Draggable divider between the chat and the canvas. Also works from the
 * keyboard (arrow keys, Enter to reset); double-click resets the width.
 */
export const ResizeHandleView = ({
  width,
  isDragging,
  onPointerDown,
  onPointerMove,
  onPointerEnd,
  onKeyDown,
  onReset,
}: ResizeHandleViewProps) => (
  <div
    role="separator"
    aria-orientation="vertical"
    aria-label="Resize chat"
    aria-valuenow={width}
    aria-valuemin={CHAT_WIDTH.min}
    aria-valuemax={CHAT_WIDTH.max}
    tabIndex={0}
    title="Drag to resize · double-click to reset"
    onPointerDown={onPointerDown}
    onPointerMove={onPointerMove}
    onPointerUp={onPointerEnd}
    onPointerCancel={onPointerEnd}
    onDoubleClick={onReset}
    onKeyDown={onKeyDown}
    className="group relative z-10 -mx-1 w-2 shrink-0 cursor-col-resize touch-none focus:outline-none"
  >
    <span
      className={`absolute inset-y-0 left-1/2 w-px -translate-x-1/2 transition-all ${
        isDragging
          ? "w-0.5 bg-indigo-500"
          : "bg-slate-200 group-hover:w-0.5 group-hover:bg-indigo-400 group-focus-visible:w-0.5 group-focus-visible:bg-indigo-500 dark:bg-slate-800"
      }`}
    />
  </div>
);
