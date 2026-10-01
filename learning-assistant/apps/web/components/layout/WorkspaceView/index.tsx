import type { RefObject } from "react";

import { Header } from "@/components/layout/Header";
import { ResizeHandle } from "@/components/layout/ResizeHandle";
import { CanvasArea } from "@/features/canvas/components/CanvasArea";
import { ChatPanel } from "@/features/chat/components/ChatPanel";
import { ChatPopup } from "@/features/chat/components/ChatPopup";
import { ChatRail } from "@/features/chat/components/ChatRail";
import { ResumeBanner } from "@/features/conversations/components/ResumeBanner";
import type { Display } from "@/types/layout";

export interface WorkspaceViewProps {
  display: Display;
  /** The row holding the chat and the canvas. */
  panelsRef: RefObject<HTMLDivElement | null>;
}

/**
 * Page layout: the header, the resume banner, then the chat and the canvas
 * side by side. A
 * previewed device layout is drawn in a centred frame; its transform makes
 * the fixed-position popup anchor to the frame instead of the window.
 *
 * The docked chat and the popup both stay mounted and only hide: a
 * `CopilotChat` without a `threadId` clears the agent's messages when it
 * mounts, so remounting one on a mode switch would wipe the conversation.
 */
export const WorkspaceView = ({ display, panelsRef }: WorkspaceViewProps) => {
  const { frameWidth, chat } = display;
  const isFramed = frameWidth !== null;

  return (
    <div
      className={`flex h-screen w-screen justify-center overflow-hidden font-sans text-slate-800 dark:text-slate-100 ${
        isFramed
          ? "bg-slate-200 py-4 dark:bg-slate-950"
          : "bg-slate-50 dark:bg-slate-900"
      }`}
    >
      <div
        style={isFramed ? { width: frameWidth } : undefined}
        className={`@container flex h-full w-full flex-col overflow-hidden bg-slate-50 dark:bg-slate-900 ${
          isFramed
            ? "transform-gpu rounded-2xl border border-slate-300 shadow-2xl dark:border-slate-700"
            : ""
        }`}
      >
        <Header />
        <div className="flex flex-1 overflow-hidden">
          <div className="flex min-w-0 flex-1 flex-col overflow-hidden">
            <ResumeBanner />
            <div ref={panelsRef} className="flex flex-1 overflow-hidden">
              {chat === "hidden" && <ChatRail />}
              <ChatPanel />
              {chat === "docked" && <ResizeHandle containerRef={panelsRef} />}
              <CanvasArea />
            </div>
          </div>
        </div>
        <ChatPopup />
      </div>
    </div>
  );
};
