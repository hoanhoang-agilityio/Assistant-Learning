import { PostgresSaver } from "@langchain/langgraph-checkpoint-postgres";

import { getPool } from "./client";
import { CHECKPOINTER_GLOBAL_KEY } from "./constants";

const globalCheckpointer = globalThis as typeof globalThis & {
  [CHECKPOINTER_GLOBAL_KEY]?: PostgresSaver;
};

/**
 * Every thread's checkpoints (messages and state), in Postgres, so a
 * conversation survives a restart. Shares the domain tables' pool.
 */
export const getThreadCheckpointer = (): PostgresSaver =>
  (globalCheckpointer[CHECKPOINTER_GLOBAL_KEY] ??= new PostgresSaver(
    getPool(),
  ));

/** Creates the checkpointer's tables. Idempotent; run once at server start. */
export const setupThreadCheckpointer = (): Promise<void> =>
  getThreadCheckpointer().setup();
