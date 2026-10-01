import { MemorySaver } from "@langchain/langgraph";
import type { Database } from "@repo/db";
import { createTestDatabase } from "@repo/db/testing";

import { USER_ROWS_GLOBAL_KEY } from "@/constants/users";

/**
 * What route tests use in place of Postgres: a fresh PGlite database per
 * test and one in-memory checkpointer. A test file wires them in with
 *
 *   vi.mock("@repo/db/client", () => import("@/services/__tests__/database-mock").then((m) => m.CLIENT_MOCK));
 *   vi.mock("@repo/db/checkpointer", () => import("@/services/__tests__/database-mock").then((m) => m.CHECKPOINTER_MOCK));
 *
 * and calls `resetTestDatabase` in `beforeEach`.
 */
export const testDatabase: { current?: Database; checkpointer: MemorySaver } = {
  checkpointer: new MemorySaver(),
};

export const CLIENT_MOCK = {
  getDatabase: (): Database => {
    if (!testDatabase.current) {
      throw new Error("Call resetTestDatabase() in beforeEach");
    }
    return testDatabase.current;
  },
};

export const CHECKPOINTER_MOCK = {
  getThreadCheckpointer: () => testDatabase.checkpointer,
  setupThreadCheckpointer: async () => {},
};

/** An empty database, and no user rows remembered from an earlier test. */
export const resetTestDatabase = async (): Promise<Database> => {
  testDatabase.current = await createTestDatabase();
  (
    globalThis as typeof globalThis & {
      [USER_ROWS_GLOBAL_KEY]?: Map<string, string>;
    }
  )[USER_ROWS_GLOBAL_KEY]?.clear();
  return testDatabase.current;
};
