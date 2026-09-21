import type { Provider } from "@repo/shared/schemas";
import type { RefObject } from "react";

import { Header } from "@/components/layout/Header";
import { ResizeHandle } from "@/components/layout/ResizeHandle";
import { CanvasShell } from "@/features/canvas/components/CanvasShell";
import { ChatPanel } from "@/features/chat/components/ChatPanel";
import { ChatRail } from "@/features/chat/components/ChatRail";

export interface WorkspaceViewProps {
  availableProviders: readonly Provider[];
  isChatOpen: boolean;
  /** The row holding the chat and the canvas. */
  panelsRef: RefObject<HTMLDivElement | null>;
}

/** Page layout: the header, then the chat and the canvas side by side. */
export const WorkspaceView = ({
  availableProviders,
  isChatOpen,
  panelsRef,
}: WorkspaceViewProps) => (
  <div className="flex h-screen w-screen flex-col overflow-hidden bg-slate-50 font-sans text-slate-800 dark:bg-slate-900 dark:text-slate-100">
    <Header availableProviders={availableProviders} />
    <div ref={panelsRef} className="flex flex-1 overflow-hidden">
      <ChatRail />
      <ChatPanel />
      {isChatOpen && <ResizeHandle containerRef={panelsRef} />}
      <CanvasShell />
    </div>
  </div>
);
