import { useRenderTool } from "@copilotkit/react-core/v2";
import { LEARNING_AGENT_ID } from "@repo/shared/constants/agents";
import { ToolParamSchemas } from "@repo/shared/schemas";

import { ToolProgress } from "@/features/chat/components/ToolProgress";
import { formatQuizSize } from "@/features/chat/utils/tool-results";

/**
 * Progress cards for every subagent tool. Called once from the app shell so
 * the renderers never unmount while a tool call is on screen.
 */
export const useToolRenderers = () => {
  useRenderTool(
    {
      name: "research",
      agentId: LEARNING_AGENT_ID,
      parameters: ToolParamSchemas.research,
      render: ({ status, parameters, result }) => (
        <ToolProgress
          tool="research"
          status={status}
          detail={parameters.topic}
          result={result}
        />
      ),
    },
    [],
  );

  useRenderTool(
    {
      name: "makeNotes",
      agentId: LEARNING_AGENT_ID,
      parameters: ToolParamSchemas.makeNotes,
      render: ({ status, result }) => (
        <ToolProgress tool="makeNotes" status={status} result={result} />
      ),
    },
    [],
  );

  useRenderTool(
    {
      name: "simplify",
      agentId: LEARNING_AGENT_ID,
      parameters: ToolParamSchemas.simplify,
      render: ({ status, parameters, result }) => (
        <ToolProgress
          tool="simplify"
          status={status}
          detail={parameters.scope === "selection" ? "selection" : undefined}
          result={result}
        />
      ),
    },
    [],
  );

  useRenderTool(
    {
      name: "generateQuiz",
      agentId: LEARNING_AGENT_ID,
      parameters: ToolParamSchemas.generateQuiz,
      render: ({ status, result }) => (
        <ToolProgress
          tool="generateQuiz"
          status={status}
          detail={formatQuizSize(result)}
          result={result}
        />
      ),
    },
    [],
  );

  useRenderTool(
    {
      name: "evaluate",
      agentId: LEARNING_AGENT_ID,
      parameters: ToolParamSchemas.evaluate,
      render: ({ status, result }) => (
        <ToolProgress tool="evaluate" status={status} result={result} />
      ),
    },
    [],
  );
};
