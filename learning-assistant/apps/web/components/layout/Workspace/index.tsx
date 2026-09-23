"use client";

import { WorkspaceView } from "@/components/layout/WorkspaceView";
import { useWorkspace } from "@/hooks/use-workspace";

/** Registers the app-wide CopilotKit hooks and lays out the panels. */
export const Workspace = () => {
  const { display, panelsRef } = useWorkspace();

  return <WorkspaceView display={display} panelsRef={panelsRef} />;
};
