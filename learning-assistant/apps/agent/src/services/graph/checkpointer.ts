import { type BaseCheckpointSaver, MemorySaver } from "@langchain/langgraph";

import { CHECKPOINTER_GLOBAL_KEY } from "../../constants/graph";

const globalCheckpointer = globalThis as typeof globalThis & {
  [CHECKPOINTER_GLOBAL_KEY]?: BaseCheckpointSaver;
};

/**
 * Thread checkpoints (messages and state) for this server process. In
 * memory, so they are lost on restart, like the runtime's own threads. Kept
 * on `globalThis` so a dev reload of this module does not forget them.
 * Postgres replaces it (plan C2, M5).
 */
export const threadCheckpointer: BaseCheckpointSaver = (globalCheckpointer[
  CHECKPOINTER_GLOBAL_KEY
] ??= new MemorySaver());
