"use client";

import { CopilotKitProvider } from "@copilotkit/react-core/v2";
import { LEARNING_AGENT_ID } from "@repo/shared/constants/agents";

import { Workspace } from "@/components/layout/Workspace";
import { COPILOT_RUNTIME_URL } from "@/constants/copilot";
import { CHAT_UI_CATALOG } from "@/features/chat/constants/chat-catalog";
import { ConversationLoadError } from "@/features/conversations/components/ConversationLoadError";
import { useAppShell } from "@/hooks/use-app-shell";

/**
 * The chat's built-in A2UI renderer draws chat `renderSurface` surfaces with
 * this catalog. `includeSchema: false` stops CopilotKit sending the catalog's
 * schemas and its generic A2UI guidelines as agent context on every run; the
 * Supervisor's own tool schemas already define the components. Module-level
 * so the provider sees a stable object.
 */
const CHAT_A2UI = { catalog: CHAT_UI_CATALOG, includeSchema: false };

export interface AppShellProps {
  /** A conversation to open and retake, from a History page link. */
  retakeId: string | null;
}

/**
 * The client root: loads the saved API key and settings, and sends both to the
 * agent on every run (the sealed key as a header, the settings in
 * `forwardedProps.settings`). Renders nothing until a key is known to be
 * saved and a conversation is open; without a key the user is sent to the
 * key page. The chats run on the open conversation's thread (see
 * `WorkspaceView`).
 */
export const AppShell = ({ retakeId }: AppShellProps) => {
  const { isReady, loadError, handleRetry, headers, properties } =
    useAppShell(retakeId);

  if (loadError) {
    return <ConversationLoadError message={loadError} onRetry={handleRetry} />;
  }
  if (!isReady) {
    return null;
  }

  return (
    <CopilotKitProvider
      runtimeUrl={COPILOT_RUNTIME_URL}
      agentId={LEARNING_AGENT_ID}
      headers={headers}
      properties={properties}
      a2ui={CHAT_A2UI}
    >
      <Workspace />
    </CopilotKitProvider>
  );
};
