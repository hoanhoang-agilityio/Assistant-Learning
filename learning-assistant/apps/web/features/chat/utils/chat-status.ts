import type { ChatStatus, RuntimeConnection } from "@/features/chat/types/chat";

/** The header badge status for a runtime connection and agent run state. */
export const getChatStatus = (
  connection: RuntimeConnection,
  isRunning: boolean,
): ChatStatus => {
  if (connection === "error") {
    return "offline";
  }

  if (connection !== "connected") {
    return "starting";
  }

  return isRunning ? "thinking" : "online";
};
