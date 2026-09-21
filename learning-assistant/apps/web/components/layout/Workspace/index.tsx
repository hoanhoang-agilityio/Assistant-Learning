"use client";

import type { Provider } from "@repo/shared/schemas";

import { WorkspaceView } from "@/components/layout/WorkspaceView";
import { useWorkspace } from "@/hooks/use-workspace";

export interface WorkspaceProps {
  /** Providers whose API key is set on the server. */
  availableProviders: readonly Provider[];
}

/** Registers the app-wide CopilotKit hooks and lays out the panels. */
export const Workspace = ({ availableProviders }: WorkspaceProps) => {
  const { isChatOpen, panelsRef } = useWorkspace();

  return (
    <WorkspaceView
      availableProviders={availableProviders}
      isChatOpen={isChatOpen}
      panelsRef={panelsRef}
    />
  );
};
