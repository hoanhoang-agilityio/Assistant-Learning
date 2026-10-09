/**
 * Runs once when the server starts. Creates the thread checkpointer's
 * tables (idempotent), so the first request does not race to do it. The
 * domain tables come from `pnpm db:migrate` (run by the Vercel build, see
 * `vercel.json`). A database that is down must not take every page down
 * with it: the failure is logged, the API routes answer 503, and the next
 * chat run tries the setup again.
 */
export const register = async () => {
  if (process.env.NEXT_RUNTIME !== "nodejs") {
    return;
  }

  const { setupThreadCheckpointer } = await import("@repo/db");
  try {
    await setupThreadCheckpointer();
  } catch (error) {
    console.error("[database] Checkpointer setup failed", error);
  }
};
