import { PostgresSaver } from "@langchain/langgraph-checkpoint-postgres";

import { getPool } from "./client";
import {
  CHECKPOINTER_GLOBAL_KEY,
  CHECKPOINTER_SETUP_GLOBAL_KEY,
} from "./constants";

const globalCheckpointer = globalThis as typeof globalThis & {
  [CHECKPOINTER_GLOBAL_KEY]?: PostgresSaver;
  [CHECKPOINTER_SETUP_GLOBAL_KEY]?: Promise<void>;
};

/**
 * Every thread's checkpoints (messages and state), in Postgres, so a
 * conversation survives a restart. Shares the domain tables' pool.
 */
export const getThreadCheckpointer = (): PostgresSaver =>
  (globalCheckpointer[CHECKPOINTER_GLOBAL_KEY] ??= new PostgresSaver(
    getPool(),
  ));

const startSetup = (): Promise<void> =>
  getThreadCheckpointer()
    .setup()
    .catch((error: unknown) => {
      globalCheckpointer[CHECKPOINTER_SETUP_GLOBAL_KEY] = undefined;
      throw error;
    });

/**
 * Creates the checkpointer's tables, once per process (idempotent). A
 * failed attempt is forgotten, so the next call tries again once the
 * database is back.
 */
export const setupThreadCheckpointer = (): Promise<void> =>
  (globalCheckpointer[CHECKPOINTER_SETUP_GLOBAL_KEY] ??= startSetup());
