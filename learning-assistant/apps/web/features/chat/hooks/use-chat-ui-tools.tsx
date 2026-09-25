import { useComponent, useRenderTool } from "@copilotkit/react-core/v2";
import {
  CHAT_CARD_TOOLS,
  DELETE_BOARD_SURFACE_TOOL,
  LEARNING_AGENT_ID,
  RENDER_SURFACE_TOOL,
  UPDATE_BOARD_SURFACE_TOOL,
} from "@repo/shared/constants/agents";
import {
  CodeExampleParamsSchema,
  ComparisonParamsSchema,
  ConceptCardParamsSchema,
  DeleteBoardSurfaceArgsSchema,
  RenderSurfaceArgsSchema,
  StepsParamsSchema,
  UpdateBoardSurfaceArgsSchema,
} from "@repo/shared/schemas";

import { DisplayToolCard } from "@/components/common/DisplayToolCard";
import { CodeExampleCard } from "@/features/chat/components/CodeExampleCard";
import { ComparisonCard } from "@/features/chat/components/ComparisonCard";
import { ConceptCard } from "@/features/chat/components/ConceptCard";
import { StepsCard } from "@/features/chat/components/StepsCard";
import {
  CHAT_CARD_DESCRIPTIONS,
  DELETE_BOARD_SURFACE_COPY,
  RENDER_SURFACE_COPY,
  UPDATE_BOARD_SURFACE_COPY,
} from "@/features/chat/constants/tools";
import {
  isBoardSurfaceResult,
  parseRemovedTitles,
} from "@/features/chat/utils/tool-results";

/**
 * The two ways the Supervisor draws UI in the chat. Fixed cards: four
 * handler-less tools registered with `useComponent`, each a known shape the
 * model picks by its description; `followUp: false` ends the run on the card
 * so it is not repeated in text. Dynamic A2UI: `renderSurface` is a server
 * tool. A chat surface is drawn by the chat's built-in A2UI renderer, so this
 * only shows progress until it arrives; a canvas surface goes to the Board,
 * so this leaves a card saying so, as do an `updateBoardSurface` edit and a
 * `deleteBoardSurface` removal. `readBoardSurface` shows nothing. Called
 * once from the app shell.
 */
export const useChatUiTools = () => {
  useComponent(
    {
      name: CHAT_CARD_TOOLS.concept,
      agentId: LEARNING_AGENT_ID,
      description: CHAT_CARD_DESCRIPTIONS.concept,
      parameters: ConceptCardParamsSchema,
      render: ConceptCard,
      followUp: false,
    },
    [],
  );

  useComponent(
    {
      name: CHAT_CARD_TOOLS.comparison,
      agentId: LEARNING_AGENT_ID,
      description: CHAT_CARD_DESCRIPTIONS.comparison,
      parameters: ComparisonParamsSchema,
      render: ComparisonCard,
      followUp: false,
    },
    [],
  );

  useComponent(
    {
      name: CHAT_CARD_TOOLS.steps,
      agentId: LEARNING_AGENT_ID,
      description: CHAT_CARD_DESCRIPTIONS.steps,
      parameters: StepsParamsSchema,
      render: StepsCard,
      followUp: false,
    },
    [],
  );

  useComponent(
    {
      name: CHAT_CARD_TOOLS.codeExample,
      agentId: LEARNING_AGENT_ID,
      description: CHAT_CARD_DESCRIPTIONS.codeExample,
      parameters: CodeExampleParamsSchema,
      render: CodeExampleCard,
      followUp: false,
    },
    [],
  );

  useRenderTool(
    {
      name: RENDER_SURFACE_TOOL,
      agentId: LEARNING_AGENT_ID,
      parameters: RenderSurfaceArgsSchema,
      // A finished chat surface is drawn by the A2UI renderer, and a
      // finished call that failed validation is retried, so neither needs a
      // card; only a view added to the Board leaves one.
      render: ({ status, parameters, result }) => {
        const target = parameters.target ?? "chat";
        if (
          status === "complete" &&
          (target === "chat" || !isBoardSurfaceResult(result))
        ) {
          return null;
        }
        return (
          <DisplayToolCard
            status={status}
            detail={target === "canvas" ? parameters.title : undefined}
            copy={RENDER_SURFACE_COPY[target]}
          />
        );
      },
    },
    [],
  );

  // A failed update is retried, so only one that went through leaves a card.
  useRenderTool(
    {
      name: UPDATE_BOARD_SURFACE_TOOL,
      agentId: LEARNING_AGENT_ID,
      parameters: UpdateBoardSurfaceArgsSchema,
      render: ({ status, parameters, result }) =>
        status === "complete" && !isBoardSurfaceResult(result) ? null : (
          <DisplayToolCard
            status={status}
            detail={parameters.title}
            copy={UPDATE_BOARD_SURFACE_COPY}
          />
        ),
    },
    [],
  );

  // Removals are announced here, in the chat, never on the Board.
  useRenderTool(
    {
      name: DELETE_BOARD_SURFACE_TOOL,
      agentId: LEARNING_AGENT_ID,
      parameters: DeleteBoardSurfaceArgsSchema,
      render: ({ status, result }) => {
        const titles = parseRemovedTitles(result);
        if (status === "complete" && !titles) {
          return null;
        }
        return (
          <DisplayToolCard
            status={status}
            detail={titles?.join(", ")}
            copy={DELETE_BOARD_SURFACE_COPY}
          />
        );
      },
    },
    [],
  );
};
