# Learning Assistant

A tutor that takes a student from a topic to scored, personalised feedback in one session: **Research → Notes → Quiz → Evaluation → Score → Feedback**. You chat on the left, and the canvas on the right shows each stage as it is built.

It is built on CopilotKit 1.72, AG-UI and A2UI. A Supervisor agent hands work to four subagents (Research, Notes, Quiz and Evaluator). The full design is in [docs/design.md](./docs/design.md) and the task breakdown is in [docs/v1-tasks.md](./docs/v1-tasks.md).

## Setup

You need Node.js 24 or later and pnpm 11 (`corepack enable` picks the version in `package.json`).

```bash
pnpm install
cp apps/web/.env.example apps/web/.env
```

Fill in `apps/web/.env` (see below). At minimum, set one provider key and `QUIZ_SEAL_SECRET`. Then start the app:

```bash
pnpm dev
```

Open <http://localhost:3000>. Keys are read on each request, so after you change `.env`, restart the dev server.

## Environment variables

All variables live in `apps/web/.env` and are read on the server only.

| Variable | Required | What it does |
| --- | --- | --- |
| `OPENAI_API_KEY` | One provider key | Enables OpenAI models |
| `ANTHROPIC_API_KEY` | One provider key | Enables Anthropic models |
| `GOOGLE_GENERATIVE_AI_API_KEY` | One provider key | Enables Google Gemini models |
| `QUIZ_SEAL_SECRET` | Yes | Secret used to encrypt the quiz answer key until Submit. Generate one with `openssl rand -base64 32` |
| `TAVILY_API_KEY` | No | Turns on web research with cited sources. Without it, research uses only the model's own knowledge and lists no sources |
| `NEXT_PUBLIC_RUNTIME_URL` | No | Base path of the CopilotKit runtime route. Defaults to `/api/copilotkit` |

The `LANGSMITH_*` entries in `.env.example` are not read by v1.

## Providers and models

Settings (the gear in the header) only lists providers whose key is set. The allowlist is in [apps/web/constants/models.ts](./apps/web/constants/models.ts):

| Provider | Models | Reasoning effort |
| --- | --- | --- |
| OpenAI | GPT-5.4 mini (default), GPT-5.4 | Effort level |
| Anthropic | Claude Sonnet 5, Claude Haiku 4.5 | Adaptive thinking or a token budget |
| Google | Gemini 3.8 Flash, Gemini 2.5 Flash | Thinking level or a token budget |

Settings also hold the question count (3–20), the learning level and the theme. They are saved in the browser and sent with every run. If a provider rejects a key, runs out of quota or does not know a model, the chat and the canvas explain what to fix.

## Scripts

Run these from the repo root. Turborepo runs them in every package.

| Command | What it does |
| --- | --- |
| `pnpm dev` | Starts the web app on port 3000 |
| `pnpm build` | Builds for production |
| `pnpm lint` | Runs ESLint with zero warnings allowed |
| `pnpm check-types` | Type-checks every package |
| `pnpm test` | Runs the Vitest suites |
| `pnpm format` | Formats `ts`, `tsx` and `md` files with Prettier |

Commits go through Husky: lint-staged formats and lints staged files, and commitlint checks for a conventional commit message.

## Architecture

```text
apps/web/                  Next.js app (UI, CopilotKit runtime, agents)
  app/api/copilotkit/      CopilotRuntime route that registers the agent
  features/agent/          Supervisor wrapper, subagents, tools, prompts, scoring
  features/canvas/         Stepper, stages, A2UI catalog and surfaces
  features/chat/           Chat panel, tool progress cards, new-topic confirmation
  features/settings/       Settings store and popover
  components/layout/       App shell, header, workspace, resize handle
packages/shared/           zod schemas, A2UI templates and shared constants
packages/eslint-config/    ESLint presets
packages/typescript-config/ tsconfig presets
```

Everything runs inside the Next.js app. `CopilotRuntime` hosts one agent, `LearningSupervisorAgent`. It is a thin wrapper around CopilotKit's `BuiltInAgent`, and on each run it does four things:

1. Reads the user's settings from `forwardedProps` and builds the Supervisor for the chosen model and reasoning effort.
2. Gives the Supervisor its subagent tools (`research`, `makeNotes`, `simplify`, `generateQuiz`, `evaluate`), each running a focused `generateObject` call.
3. Passes the Supervisor a trimmed state, never the full notes or quiz.
4. Turns each tool result into an AG-UI `STATE_DELTA`, so the canvas updates without the LLM copying data into state.

A few rules keep the flow reliable:

- **The quiz stays sealed.** The answer key is encrypted into state, and no snapshot or delta before Submit contains the correct answers.
- **Submit is graded in code.** The Submit button sends an A2UI action, and the wrapper grades the quiz before the Supervisor runs. The LLM only writes the chat summary.
- **Fixed stages are templates.** Research, Quiz, Evaluation and Score are A2UI templates from `packages/shared/src/a2ui/templates/`, bound to agent state. Only the Feedback stage is generated: the Evaluator writes it with a small Feedback catalog, and a plain summary is shown if it cannot be drawn.
- **A new topic needs confirmation.** When notes or a quiz exist, the chat asks before anything is cleared (human-in-the-loop). The chat history is kept.
- **Failures can be retried.** A failed step sets `status.error`. The canvas shows it with a Retry button, and the Supervisor explains it in chat.

v1 keeps state for the session only and has no auth or database. v2 moves the agents to Python (LangGraph and FastAPI) and adds auth, persistence and multiple conversations. See [docs/design.md](./docs/design.md#v2-migration-langgraph--fastapi) for the plan.
