"use client";

import { CopilotKitProvider } from "@copilotkit/react-core/v2";
import { LEARNING_AGENT_ID } from "@repo/shared/constants/agents";
import type { Provider } from "@repo/shared/schemas";

import { Workspace } from "@/components/layout/Workspace";
import { COPILOT_RUNTIME_URL } from "@/constants/copilot";
import { useAppShell } from "@/hooks/use-app-shell";

export interface AppShellProps {
  /** Providers whose API key is set on the server. */
  availableProviders: readonly Provider[];
}

/**
 * The client root: loads saved settings, keeps the theme class in sync, and
 * sends the settings to the agent in `forwardedProps.settings` on every run.
 */
export const AppShell = ({ availableProviders }: AppShellProps) => {
  const { properties } = useAppShell(availableProviders);

  return (
    <CopilotKitProvider
      runtimeUrl={COPILOT_RUNTIME_URL}
      agentId={LEARNING_AGENT_ID}
      properties={properties}
      // The dev Inspector's floating button covers the header's Settings.
      enableInspector={false}
    >
      <Workspace availableProviders={availableProviders} />
    </CopilotKitProvider>
  );
};
