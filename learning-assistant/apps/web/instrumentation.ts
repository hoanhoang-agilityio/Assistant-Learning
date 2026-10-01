/**
 * Runs once when the server starts. Creates the thread checkpointer's
 * tables (idempotent), so the first request does not race to do it. The
 * domain tables come from `pnpm db:migrate`.
 */
export const register = async () => {
  if (process.env.NEXT_RUNTIME !== "nodejs") {
    return;
  }

  const { setupThreadCheckpointer } = await import("@repo/db");
  await setupThreadCheckpointer();
};
