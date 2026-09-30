# v2 Spike Findings (M0)

2026-09-30 · Branch `spike/v2-langchain-agent`. Throwaway code in `spikes/v2` (and `spikes/v2-h2` for the H2 server); see [spikes/v2/README.md](../spikes/v2/README.md) to re-run. Plan: [v2-migration-plan.md](./v2-migration-plan.md).

Every check below went through the real `CopilotRuntime` HTTP handler (`/agent/learning/run`, `/connect`, `/stop`) with the A2UI middleware on, exactly as the Next route builds it. Most runs use a scripted chat model for determinism; S2/S3/A1/S8 were also run against `gpt-5.4-mini`.

## Versions tested

| Package | Version | Note |
| --- | --- | --- |
| `@copilotkit/runtime` | 1.72.0 | Already pulls `langchain` 1.5.11, `@langchain/langgraph` 1.4.15, `@langchain/core` 1.2.11, `@ag-ui/langgraph` 0.0.43 |
| `@copilotkit/sdk-js` | 1.72.0 | Peer `zod ^3`, works with zod 4.6.5; pins `@ag-ui/langgraph` 0.0.42 (a second copy) |
| `@langchain/openai` | 1.6.0 | Needs `useResponsesApi: true` for gpt-5.4-mini tools + reasoning |
| `@langchain/langgraph-checkpoint-postgres` | 1.0.5 | Saver and `PostgresStore` |
| `@langchain/langgraph-cli` / `-api` | 1.5.1 | H2 only; needs `@langchain/langgraph` ≥ 1.4.18 (newer than the runtime's 1.4.15) |
| Postgres | 16.11 | Local, throwaway |

## Answers

| # | Question | Answer | Evidence |
| --- | --- | --- | --- |
| S1 | H1 / H2 / H3? | **H1 works.** `LangGraphAgent` accepts a `client`; a 150-line in-process client (11 SDK methods over the compiled graph) runs the graph inside the Next route. H2 works but the client can forge server config (below). H3 is H1's adapter behind HTTP, no gain | `spike-core`, `spike-h2` |
| S2 | `copilotkitMiddleware` + JS `createAgent`? | **Works**: tools, tool-call streaming, text streaming, frontend tools (intercepted, run ends, client result resumes the thread). Import is `copilotkitMiddleware` from `@copilotkit/sdk-js/langgraph`; `/langchain` is deprecated and warns on import. Both cited issues (#3008, #3886) are closed. **But `useAgentContext` entries never reach the model** on this path | `spike-core`, `spike-frontend-tools`, `spike-context` |
| S3 | Drafts mid-tool? | **Works with `dispatchCustomEvent("manually_emit_state", fullState)`** → `STATE_SNAPSHOT` per emit. **`copilotkitEmitState` does not work** with the v2 adapter (its event name is not handled; 0 snapshots). No deltas: each emit is a full snapshot of every client-visible key, so keep the 120 ms throttle. Inner model calls must carry metadata `emit-messages: false`, `emit-tool-calls: false` (not the `copilotkit:`-prefixed keys `copilotkitCustomizeConfig` writes) or their tokens show up in chat | `spike-core ag-ui` vs `copilotkit`, `spike-real` |
| S4 | Client `setState` vs checkpoint? | **The client's whole state is the run input and overwrites the checkpoint** for every key it sends (a stale `stage` replaced the server's). Fix that works: the client declares `input_schema` keys = client-writable keys only, `output_schema` keys = client-visible keys only. Then the client cannot overwrite `stage` or forge `summary`, and server-only keys never reach it | `spike-core`, `spike-filter` |
| S5 | Where do `forwardedProps` arrive? | Not in the graph: the adapter spreads them into the SDK payload, and a LangGraph server drops them. With H1 our client picks them (`settings`, `a2uiAction`) into the run `context`. A quiz Submit also makes the A2UI middleware append a synthetic `ai` tool call + `tool` result ("User performed action … Context: {answers}") to the thread, persisted in the checkpoint | `spike-core` |
| S6 | `a2ui_operations` from a LangChain tool? `validateA2UIComponents` reusable? | **Yes and yes.** A tool returning `JSON.stringify({ a2ui_operations })` becomes an `ACTIVITY_SNAPSHOT` (`a2ui-surface`); an invalid tree returns the toolkit's error text to the model unchanged | `spike-core` |
| S7 | Change model input without writing state? | **Yes**, `wrapModelCall` replacing `request.messages`: model saw summary + messages after the boundary, checkpoint kept all messages. The middleware must declare `stateSchema` for the fields it reads; without it `request.state` holds only `messages` | `spike-core` |
| S8 | Secrets in checkpoints or traces? | Runtime `context` **is recorded in every LLM run's trace (`extra.options.context`)**, so a key in context goes to LangSmith. A key built into `ChatOpenAI` per request is in no trace, checkpoint or browser event. Inbound `x-*` headers (incl. `x-openai-key-sealed`) land in `configurable.copilotkit_forwarded_headers` unless `forwardHeaders: { deny: ["authorization"], denyPrefixes: ["x-"] }`; they are not added to OpenAI requests in H1 | `spike-core`, `spike-real`, `spike-frontend-tools` |
| S9 | `PostgresSaver` / store? | `setup()` is idempotent (~30 ms), state survives a restart, `deleteThread` removes checkpoints, blobs and writes. `PostgresStore` exists in JS (namespaced put/get/search/delete). **Reload is broken out of the box**: the runtime's `/connect` replays events from process memory only, so after a restart (or on another instance) it returns nothing. A 40-line `CheckpointRunner` (runtime `runner` option) rebuilds the snapshots from the checkpoint | `spike-postgres`, `spike-connect` |

## Other things the spikes surfaced

| # | Finding | Consequence |
| --- | --- | --- |
| F-1 | The browser stream carries **all graph state and model inputs**: `RAW` events plus a `rawEvent` field on every event. Turn 1 of a toy run was 334 KB of SSE. Server-only `summary` reached the browser 14 times | Drop `RAW` and strip `rawEvent` in an AG-UI middleware on the agent (`agent.use`). Verified: 29 KB → 8 KB, no server-only data |
| F-2 | H2: `forwardedProps.config.configurable.userId` from the browser **overrides** the server's `assistantConfig` value, and browser `x-*` headers become top-level `configurable` keys on the server | H2 would need the Next route to strip `config`/headers and the server to authenticate Next. H1 blocks it (verified) |
| F-3 | H2 production: the LangGraph JS dev server says it is for development; production is LangSmith Deployment or its self-hosted image (Postgres + Redis) | Extra service, cost and version drift (needs a newer langgraph than the runtime) |
| F-4 | `withStructuredOutput(...).stream()` yields **one** object (the final), with every method; `functionCalling` errors on the Responses API | A1: stream raw text with `response_format: json_schema` + `parsePartialJson`, validate the final with zod (127 partials, first at 1.2 s) |
| F-5 | `ChatOpenAI` defaults to Chat Completions, which rejects tools + reasoning for gpt-5.4-mini (400) | `useResponsesApi: true` |
| F-6 | A throwing tool fails the whole run by default | `toolErrorMiddleware({ onError })`. The error result then arrives only in the final `MESSAGES_SNAPSHOT`, not as a `TOOL_CALL_RESULT` event |
| F-7 | Two tool calls in one step writing the same key (e.g. `stage`) kill the run; the client gets a lone `RUN_ERROR` with no `RUN_STARTED` | Parallel tool calls off, or reducers for shared keys |
| F-8 | Stop: the adapter cancels with an id the in-process client never sees, so the graph ran on. Fixed in the adapter (cancel by thread); tools must honour `config.signal`. Stop leaves an `ai` tool call with no result, and OpenAI rejects that history on the next turn (`400 No tool output found`) | Keep the `repairToolHistory` step (in the context builder) |
| F-9 | Provider errors reach the client as `RUN_ERROR` with raw OpenAI text; the adapter then emits more events and the runtime logs an AG-UI protocol error | Keep a readable-error mapping (today's `explainRunErrors`) |
| F-10 | `/connect` replay and `/stop` both depend on in-process runner memory (`ɵGLOBAL_STORE`) | Single instance, or sticky threads, until a shared runner exists |
| F-11 | The adapter drops tool args that arrive in the same chunk as the tool name (seen with the scripted model; OpenAI sends the name first) | The F1 fake model must stream name and args in separate chunks |

## Not verified

| Item | Why | Needed |
| --- | --- | --- |
| Clerk (exit criterion "runs behind Clerk") | Needs a Clerk app and keys; signing up is the user's to do | B1 keys; then `auth()` in the route, 401 without session. `@clerk/nextjs` 7.9.7 peer range covers Next 16.3 |
| Browser client with `STATE_SNAPSHOT`-only updates and `/connect` on thread switch | Spikes drove the HTTP handler, not React | A Next route wired to the spike graph, checked in the browser pane |
| Board drafts from `TOOL_CALL_ARGS` | Args do stream (7 deltas from the real model); writing `boardDraft` as a `STATE_DELTA` from an AG-UI middleware was not tried | Try in A8 |
| CopilotKit's own thread APIs (`useThreads`) | Out of scope for the spikes | Check before building C4/D1 |
