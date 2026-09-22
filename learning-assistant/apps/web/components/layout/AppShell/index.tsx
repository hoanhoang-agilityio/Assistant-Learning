"use client";

import { CopilotKitProvider } from "@copilotkit/react-core/v2";
import { LEARNING_AGENT_ID } from "@repo/shared/constants/agents";

import { Workspace } from "@/components/layout/Workspace";
import { COPILOT_RUNTIME_URL } from "@/constants/copilot";
import { useAppShell } from "@/hooks/use-app-shell";

/**
 * The client root: loads the saved API key and settings, and sends both to the
 * agent on every run (the sealed key as a header, the settings in
 * `forwardedProps.settings`). Renders nothing until a key is known to be
 * saved; without one the user is sent to the key page.
 */
export const AppShell = () => {
  const { isReady, headers, properties } = useAppShell();

  if (!isReady) {
    return null;
  }

  return (
    <CopilotKitProvider
      runtimeUrl={COPILOT_RUNTIME_URL}
      agentId={LEARNING_AGENT_ID}
      headers={headers}
      properties={properties}
    >
      <Workspace />
    </CopilotKitProvider>
  );
};
