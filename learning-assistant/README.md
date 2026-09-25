# Learning Assistant

A tutor that takes a student from a topic to scored, personalised feedback in one session: **Research → Learning Material → Quiz → Evaluation → Score → Feedback**. You chat on the left, and the canvas on the right shows each stage as it is built.

It is built on CopilotKit 1.72, AG-UI and A2UI. A Supervisor agent hands work to four subagents (Research, Material, Quiz and Evaluator). The full design is in [docs/design.md](./docs/design.md) and the task breakdown is in [docs/v1-tasks.md](./docs/v1-tasks.md).

## Setup

You need Node.js 24 or later and pnpm 11 (`corepack enable` picks the version in `package.json`).

```bash
pnpm install
cp apps/web/.env.example apps/web/.env
```

Fill in `apps/web/.env` (see below). At minimum, set `API_KEY_SEAL_SECRET` and `QUIZ_SEAL_SECRET`. Then start the app:

```bash
pnpm dev
```

Open <http://localhost:3000>. You are sent to the API key page first: enter your own OpenAI API key. The server checks it with OpenAI, then returns it sealed (AES-256-GCM with `API_KEY_SEAL_SECRET`). The browser keeps only the sealed key, in `sessionStorage`, so it is cleared when the tab closes. Without a saved key, the assistant sends you back to the key page. After you change `.env`, restart the dev server.

## Using the app

The screen has two parts. The **chat** is where you ask for things; it can be docked on the left, float as a popup, or be hidden (`Pop out`, `Collapse` and the resize handle are in its header). The **canvas** has two tabs: **Learning path**, a six-stage stepper (Research → Learning Material → Quiz → Evaluation → Score → Feedback), and **Board**, where views the assistant draws for you are kept. Every action shows a small card in the chat, such as "Research ready: photosynthesis", and its result appears on the canvas.

You can use the app in nine ways. The messages are examples; any wording that says the same thing works, in any language.

### 1. Learn a topic step by step

| Step              | Say or do                                                                                | What happens                                                                                        |
| ----------------- | ---------------------------------------------------------------------------------------- | --------------------------------------------------------------------------------------------------- |
| Research          | "Research JavaScript closures"                                                           | The Research stage fills with a reading, key insight, flashcards and sources                        |
| Learning material | "Make learning material"                                                                 | Study notes appear in the Learning Material stage                                                   |
| Quiz              | "Quiz me"                                                                                | A multiple-choice quiz with your question count appears. The answers stay sealed                    |
| Answer and submit | Pick an option for each question, then press **Submit**                                  | The quiz is graded in code. Evaluation, Score (Novice, Practitioner or Master) and Feedback fill in |
| Reflect           | In Feedback, rate the session, write a note and press **Save reflection & send to chat** | The assistant answers your note and suggests a next step                                            |

Each step needs the one before it. If you skip ahead ("make a quiz" with no material), the assistant says what is missing and offers to do it.

### 2. Do everything in one message (Autopilot)

"Teach me black holes end to end" or "Do everything on black holes" runs research, learning material and a quiz one after another, then stops so you can answer the quiz. The assistant never answers or grades it for you.

### 3. Work with the learning material

- **Original / Simplified**: switch between the notes and a simpler rewrite.
- **Simplify all**, or "Simplify my learning material": rewrites the whole set into the Simplified view.
- **Simplify selection**: press **Edit**, select a passage in the text, then press **Simplify selection**. Only that passage is rewritten.
- **Edit**: change the notes yourself. They are saved for the session. A quiz written from the old notes is cleared, and the assistant offers a new one when you ask about it.

### 4. Practise with the quiz

- **Retake** clears your answers so you can try the same questions again.
- **New questions**, or "Give me new questions": writes a new quiz and clears the old results.
- Answer every question and say "grade my answers" in the chat instead of pressing **Submit**.
- On the Feedback card, a **Review …** link for your weakest concept takes you back to the learning material.

### 5. Get a quick visual answer in the chat

Side questions get a card instead of a wall of text. They do not change the canvas.

| Ask                                           | You get                                     |
| --------------------------------------------- | ------------------------------------------- |
| "What is a closure?"                          | A concept card                              |
| "let vs const, what is the difference?"       | A comparison table                          |
| "How does the event loop work?"               | Numbered steps                              |
| "Show me a code example of a closure"         | A code card                                 |
| "Give me a small panel about primitive types" | A compact panel mixing text, lists and tips |

### 6. Build views on the Board

Ask for something to keep, or mention the board or the canvas, and the assistant draws a wide view on the **Board** tab. It needs no research first.

- **Create**: "Show me all IPA symbols on the board", "Put a cheat sheet of Git commands on the canvas".
- **Edit**: "Add a tip about memory leaks to the cheat sheet". The view keeps its place and updates.
- **Delete**: "Delete the cheat sheet" or "Clear the board". The Board keeps up to eight views.

### 7. Switch to a new topic

When learning material or a quiz exists and you ask about a different topic, the chat shows a card. **Start new topic** clears the canvas and researches the new topic; **Keep current topic** leaves everything as it is. The chat history is kept either way.

### 8. Change settings and the display

Open **Settings** in the header, or ask in the chat.

| Setting        | In the chat                                                  |
| -------------- | ------------------------------------------------------------ |
| Question count | "Use 5 questions for my quizzes" (3 to 20)                   |
| Learning level | "Make it advanced" (beginner, intermediate, advanced)        |
| Theme          | "Switch to light mode", "Use my device theme"                |
| Chat layout    | "Pop out the chat", "Dock the chat", "Hide the chat"         |
| Device preview | "Show me the tablet layout", "Go back to the automatic view" |

Settings apply to the next research, material or quiz; existing content is not regenerated. The **Account** group in Settings is where you change your OpenAI key.

### 9. Stop or retry

While a step runs, its chat card has a **Stop** button. If a step fails, the stage shows the error with a **Retry** button, and the assistant explains what went wrong in the chat.

## Environment variables

All variables live in `apps/web/.env` and are read on the server only.

| Variable                  | Required | What it does                                                                                                                         |
| ------------------------- | -------- | ------------------------------------------------------------------------------------------------------------------------------------ |
| `API_KEY_SEAL_SECRET`     | Yes      | Secret used to encrypt the user's OpenAI key, so the browser never stores the plain key. Generate one with `openssl rand -base64 32` |
| `QUIZ_SEAL_SECRET`        | Yes      | Secret used to encrypt the quiz answer key until Submit. Generate one with `openssl rand -base64 32`                                 |
| `TAVILY_API_KEY`          | No       | Turns on web research with cited sources. Without it, research uses only the model's own knowledge and lists no sources              |
| `NEXT_PUBLIC_RUNTIME_URL` | No       | Base path of the CopilotKit runtime route. Defaults to `/api/copilotkit`                                                             |
| `LANGSMITH_TRACING`       | No       | Set to `true` to send every LLM call to LangSmith                                                                                    |
| `LANGSMITH_API_KEY`       | No       | LangSmith API key. Required when `LANGSMITH_TRACING` is `true`                                                                       |
| `LANGSMITH_PROJECT`       | No       | LangSmith project the traces go to. Defaults to `default`                                                                            |
| `LANGSMITH_ENDPOINT`      | No       | LangSmith API URL. Defaults to `https://api.smith.langchain.com`; use `https://eu.api.smith.langchain.com` for the EU region         |

With tracing on, each turn of the conversation is one `learning` trace. Its Supervisor steps (`supervisor`) and subagent tool calls (`research`, `makeMaterial`, `generateQuiz`…) are nested under it, each subagent with its own LLM calls. Every trace carries the chat's `thread_id`, so LangSmith's **Threads** tab groups a conversation's turns together.

## Model

Every agent uses OpenAI's `gpt-5.4-mini` with low reasoning effort, called with the user's own key. Both are set in [apps/agent/src/constants/openai.ts](./apps/agent/src/constants/openai.ts).

Settings hold the question count (3–20), the learning level, the theme, and a link to change the API key. They are saved in the browser and sent with every run. If OpenAI rejects the key, the quota runs out or the model is not available, the chat and the canvas explain what to fix.

## Scripts

Run these from the repo root. Turborepo runs them in every package.

| Command            | What it does                                     |
| ------------------ | ------------------------------------------------ |
| `pnpm dev`         | Starts the web app on port 3000                  |
| `pnpm build`       | Builds for production                            |
| `pnpm lint`        | Runs ESLint with zero warnings allowed           |
| `pnpm check-types` | Type-checks every package                        |
| `pnpm test`        | Runs the Vitest suites                           |
| `pnpm format`      | Formats `ts`, `tsx` and `md` files with Prettier |

Commits go through Husky: lint-staged formats and lints staged files, and commitlint checks for a conventional commit message.

## Architecture

```text
apps/web/                  Next.js app (UI, CopilotKit runtime)
  app/api/copilotkit/      CopilotRuntime route that registers the agent
  features/canvas/         Stepper, stages, A2UI catalog and surfaces
  features/chat/           Chat panel, tool progress cards, new-topic confirmation
  features/settings/       Settings store and popover
  components/layout/       App shell, header, workspace, resize handle
apps/agent/                @repo/agent: Supervisor wrapper, subagents, tools, prompts, scoring
packages/shared/           zod schemas, A2UI templates and shared constants
packages/eslint-config/    ESLint presets
packages/typescript-config/ tsconfig presets
```

Everything runs inside the Next.js app: the runtime route imports `@repo/agent`, so the agent runs in the same process. `CopilotRuntime` hosts one agent, `LearningSupervisorAgent`. It is a thin wrapper around CopilotKit's `BuiltInAgent`, and on each run it does four things:

1. Reads the user's settings from `forwardedProps` and builds the Supervisor with the user's OpenAI key.
2. Gives the Supervisor its subagent tools (`research`, `makeMaterial`, `simplify`, `generateQuiz`, `evaluate`), each running a focused `generateObject` call.
3. Passes the Supervisor a trimmed state, never the full learning material or quiz.
4. Turns each tool result into an AG-UI `STATE_DELTA`, so the canvas updates without the LLM copying data into state.

A few rules keep the flow reliable:

- **The quiz stays sealed.** The answer key is encrypted into state, and no snapshot or delta before Submit contains the correct answers.
- **Submit is graded in code.** The Submit button sends an A2UI action, and the wrapper grades the quiz before the Supervisor runs. The LLM only writes the chat summary.
- **Fixed stages are templates.** Research, Quiz, Evaluation and Score are A2UI templates from `packages/shared/src/a2ui/templates/`, bound to agent state. Only the Feedback stage is generated: the Evaluator writes it with a small Feedback catalog, and a plain summary is shown if it cannot be drawn.
- **A new topic needs confirmation.** When learning material or a quiz exists, the chat asks before anything is cleared (human-in-the-loop). The chat history is kept.
- **Failures can be retried.** A failed step sets `status.error`. The canvas shows it with a Retry button, and the Supervisor explains it in chat.

v1 keeps state for the session only and has no auth or database. v2 moves the agents to Python (LangGraph and FastAPI) and adds auth, persistence and multiple conversations. See [docs/design.md](./docs/design.md#v2-migration-langgraph--fastapi) for the plan.
