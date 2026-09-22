"use client";

import { WorkspaceView } from "@/components/layout/WorkspaceView";
import { useWorkspace } from "@/hooks/use-workspace";

/** Registers the app-wide CopilotKit hooks and lays out the panels. */
export const Workspace = () => {
  const { isChatOpen, panelsRef } = useWorkspace();

  return <WorkspaceView isChatOpen={isChatOpen} panelsRef={panelsRef} />;
};
