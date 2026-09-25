import type { Context } from "@ag-ui/client";

import { A2UI_CONTEXT_PREFIX } from "@/features/agent/constants/agents";

/**
 * The context without CopilotKit's A2UI entries. They describe a generic
 * `render_a2ui` tool this app does not give the Supervisor (its
 * `renderSurface` is typed to the app's catalogs), so they only cost tokens
 * and could send it after a tool that does not exist. The A2UI middleware
 * reads the context before the agent runs, so it still gets them.
 */
export const dropA2UIContext = (context: Context[]): Context[] =>
  context.filter(
    ({ description }) => !description.startsWith(A2UI_CONTEXT_PREFIX),
  );
