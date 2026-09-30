# v2 spikes (throwaway)

Outside the pnpm workspace on purpose. Findings: [docs/v2-spike-findings.md](../../docs/v2-spike-findings.md).

```bash
pnpm install --ignore-workspace
```

Postgres for `spike-postgres` / `spike-connect`: any server at `postgres://spike@localhost:55432/spikes` (see `src/env.ts`). Keys come from `apps/web/.env`; tracing is forced off.

| Script | Covers |
| --- | --- |
| `npx tsx src/spike-core.ts ag-ui` (or `copilotkit`) | S1–S8 on H1 with a scripted model |
| `npx tsx src/spike-filter.ts` | Schema key whitelists + `RAW`/`rawEvent` filter |
| `npx tsx src/spike-context.ts` | `useAgentContext` through `copilotkitMiddleware` |
| `npx tsx src/spike-frontend-tools.ts` | Frontend tool round trip, header deny-list |
| `npx tsx src/spike-edge.ts` (`TOOL_ERRORS=1`) | Parallel writes, throwing tool, Stop |
| `npx tsx src/spike-real.ts`, `spike-structured.ts`, `spike-dangling.ts` | Real `gpt-5.4-mini` (costs a few cents) |
| `npx tsx src/spike-postgres.ts`, then `KEEP=1 …` + `npx tsx src/spike-connect.ts` (`RUNNER=checkpoint`) | S9 and reload in a fresh process |
| `npx tsx src/spike-h2.ts` | H2; start `../v2-h2` first with `./node_modules/.bin/langgraphjs dev --port 2024 --no-browser` |
