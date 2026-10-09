# Learning Assistant

A tutor that takes a student from a topic to scored, personalised feedback in one session: **Research → Learning Material → Quiz → Evaluation → Score → Feedback**. You chat on the left, and the canvas on the right shows each stage as it is built.

It is built on CopilotKit 1.72, AG-UI, A2UI and LangChain.js. A Supervisor agent hands work to four subagents (Research, Material, Quiz and Evaluator). You sign in with Clerk, each topic is its own conversation that you can come back to, and the assistant remembers what you found hard across topics. The full design is in [docs/design.md](./docs/design.md), the v1 task breakdown in [docs/v1-tasks.md](./docs/v1-tasks.md) and the v2 migration in [docs/v2-migration-plan.md](./docs/v2-migration-plan.md).

## Setup

You need Node.js 24 or later, pnpm 11 (`corepack enable` picks the version in `package.json`), Docker (or your own Postgres 16), a Clerk account and an OpenAI API key.

```bash
pnpm install
cp apps/web/.env.example apps/web/.env
```

Then set up the four things `apps/web/.env` needs.

**1. Secrets.** Generate `API_KEY_SEAL_SECRET` and `QUIZ_SEAL_SECRET`, each with `openssl rand -base64 32`.

**2. Clerk (sign-in).**

1. Create an application at <https://dashboard.clerk.com> and pick the sign-in methods you want (email, Google…). The development instance needs no domain.
2. Under **API Keys**, copy the publishable key (`pk_test_…`) into `NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY` and the secret key (`sk_test_…`) into `CLERK_SECRET_KEY`.
3. Optional: to delete a user's data when they are deleted in Clerk, add a webhook endpoint under **Webhooks** pointing at `https://<your host>/api/webhooks/clerk`, subscribed to `user.deleted`, and copy its signing secret into `CLERK_WEBHOOK_SIGNING_SECRET`. Locally, Clerk can only reach it through a tunnel (for example `ngrok http 3000`); without the secret the endpoint answers 400 and nothing else changes.

The app has its own sign-in and sign-up pages (`/sign-in`, `/sign-up`). The browser only shows Clerk's UI; the Next.js server checks the session on every page and API route, and the agent gets the user's id from the server, never from the browser.

**3. Postgres.** `docker compose up -d` starts Postgres 16 with the user, password and database that `DATABASE_URL` in `.env.example` already names. To use your own server, create a database and set `DATABASE_URL` to it (`postgres://user:password@host:5432/database`). Then create the app's tables:

```bash
docker compose up -d
pnpm db:migrate
```

`pnpm db:migrate` applies the migrations in `packages/db/drizzle/` (users, settings, conversations, research, learning material, quiz attempts and long-term memory). The conversation checkpoints get their own tables, which the server creates when it starts. Run `pnpm db:migrate` again after pulling a change to `packages/db/src/schema.ts`. On Vercel, `apps/web/vercel.json` runs the migrations before every build, so a deploy brings its database up to date; the build fails if `DATABASE_URL` is missing or wrong. While the database is down or behind, the API routes answer 503 instead of 500.

**4. Optional.** `TAVILY_API_KEY` for web research with sources, and the `LANGSMITH_*` variables for tracing (see [Environment variables](#environment-variables)).

Then start the app:

```bash
pnpm dev
```

Open <http://localhost:3000> and sign in. You are then sent to the API key page: enter your own OpenAI API key. The server checks it with OpenAI, then returns it sealed (AES-256-GCM with `API_KEY_SEAL_SECRET`). The browser keeps only the sealed key, in `sessionStorage`, so it is cleared when the tab closes. Without a saved key, the assistant sends you back to the key page. After you change `.env`, restart the dev server.

## Using the app

The screen has two parts. The **chat** is where you ask for things; it can be docked on the left, float as a popup, or be hidden (`Pop out`, `Collapse` and the resize handle are in its header). The **canvas** has two tabs: **Learning path**, a six-stage stepper (Research → Learning Material → Quiz → Evaluation → Score → Feedback), and **Board**, where views the assistant draws for you are kept. Every action shows a small card in the chat, such as "Research ready: photosynthesis", and its result appears on the canvas.

You can use the app in ten ways. The messages are examples; any wording that says the same thing works, in any language.

### 1. Learn a topic step by step

| Step              | Say or do                                               | What happens                                                                                        |
| ----------------- | ------------------------------------------------------- | --------------------------------------------------------------------------------------------------- |
| Research          | "Research JavaScript closures"                          | The Research stage fills with a reading, key insight, flashcards and sources                        |
| Learning material | "Make learning material"                                | Study notes appear in the Learning Material stage                                                   |
| Quiz              | "Quiz me"                                               | A multiple-choice quiz with your question count appears. The answers stay sealed                    |
| Answer and submit | Pick an option for each question, then press **Submit** | The quiz is graded in code. Evaluation, Score (Novice, Practitioner or Master) and Feedback fill in |

Each step needs the one before it. If you skip ahead ("make a quiz" with no material), the assistant says what is missing and offers to do it.

### 2. Do everything in one message (Autopilot)

"Teach me black holes end to end" or "Do everything on black holes" runs research, learning material and a quiz one after another, then stops so you can answer the quiz. The assistant never answers or grades it for you.

### 3. Work with the learning material

- **Original / Simplified**: switch between the notes and a simpler rewrite.
- **Simplify all**, or "Simplify my learning material": rewrites the whole set into the Simplified view.
- **Simplify selection**: press **Edit**, select a passage in the text, then press **Simplify selection**. Only that passage is rewritten.
- **Edit**: change the notes yourself. The edit reaches the assistant with your next message and stays in the conversation. A quiz written from the old notes is cleared, and the assistant offers a new one when you ask about it.

### 4. Practise with the quiz

- **Retake** clears your answers so you can try the same questions again. The **Progress** page has a Retake button for every topic you were graded on.
- Answers you have picked are kept as you go: a reload, or switching to another conversation and back, brings them back.
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

Each topic is its own conversation. Press **New topic** in the conversation list on the left to start one; the conversation you were in keeps its chat, canvas and Board. If you ask about a different topic in a conversation that already has learning material or a quiz, the assistant tells you to press **New topic**.

The list shows each conversation's title, stage, status (active, completed, or abandoned after a week untouched) and latest score. Search it, rename a conversation with the pencil, or delete it for good with the bin (it asks first). Opening a conversation, or reloading the page, brings back its chat, canvas and Board, and a banner says where you left off.

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

### 10. See your progress and what the assistant remembers

- **Progress** (header): one card per topic you were graded on, with your latest and best score, a chart of every attempt, the mastery of each concept in your latest attempt, and **Retake**, which opens that conversation with the quiz ready to take again.
- **Settings → Memory**: what the assistant keeps about you across conversations. Your profile (level, explanation style, language) is noticed from what you write, and you can edit it here; what you set yourself is kept until you change or forget it. Concepts keep your mastery over every graded quiz; weak ones get extra questions in new quizzes. Topics keep your best and latest score. **Forget** removes any of them (it asks first), and the assistant reads it no more from the next message on. Deleting a conversation also removes its topic and recounts your concepts.

## Environment variables

All variables live in `apps/web/.env` and are read on the server only, except `NEXT_PUBLIC_*`, which the browser also sees.

| Variable                            | Required | What it does                                                                                                                         |
| ----------------------------------- | -------- | ------------------------------------------------------------------------------------------------------------------------------------ |
| `NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY` | Yes      | Clerk publishable key (`pk_…`), used by the sign-in UI in the browser                                                                |
| `CLERK_SECRET_KEY`                  | Yes      | Clerk secret key (`sk_…`). The server verifies every session with it; it never reaches the browser                                   |
| `API_KEY_SEAL_SECRET`               | Yes      | Secret used to encrypt the user's OpenAI key, so the browser never stores the plain key. Generate one with `openssl rand -base64 32` |
| `QUIZ_SEAL_SECRET`                  | Yes      | Secret used to encrypt the quiz answer key until Submit. Generate one with `openssl rand -base64 32`                                 |
| `TAVILY_API_KEY`                    | No       | Turns on web research with cited sources. Without it, research uses only the model's own knowledge and lists no sources              |
| `DATABASE_URL`                      | Yes      | Postgres connection string. Conversations, their checkpoints, quiz attempts and settings live there                                  |
| `CLERK_WEBHOOK_SIGNING_SECRET`      | No       | Signing secret of a Clerk webhook endpoint at `/api/webhooks/clerk`; deleting a user in Clerk then deletes their data here           |
| `NEXT_PUBLIC_RUNTIME_URL`           | No       | Base path of the CopilotKit runtime route. Defaults to `/api/copilotkit`                                                             |
| `LANGSMITH_TRACING`                 | No       | Set to `true` to send every LLM call to LangSmith                                                                                    |
| `LANGSMITH_API_KEY`                 | No       | LangSmith API key. Required when `LANGSMITH_TRACING` is `true`                                                                       |
| `LANGSMITH_PROJECT`                 | No       | LangSmith project the traces go to. Defaults to `default`                                                                            |
| `LANGSMITH_ENDPOINT`                | No       | LangSmith API URL. Defaults to `https://api.smith.langchain.com`; use `https://eu.api.smith.langchain.com` for the EU region         |
| `LANGSMITH_TRACING_SAMPLING_RATE`   | No       | Share of turns to trace, from 0 to 1, to stay under LangSmith's monthly cap                                                          |

With tracing on, each turn of the conversation is one `learning` trace. Its Supervisor steps (`supervisor`) and subagent tool calls (`research`, `makeMaterial`, `generateQuiz`…) are nested under it, each subagent with its own LLM calls. Every trace carries the chat's `thread_id`, so LangSmith's **Threads** tab groups a conversation's turns together, and the signed-in Clerk `user_id`.

## Model

Every agent uses OpenAI's `gpt-5.4-mini` with low reasoning effort, called with the user's own key. Both are set in [apps/agent/src/constants/openai.ts](./apps/agent/src/constants/openai.ts).

Settings hold the question count (3–20), the learning level, the theme, and a link to change the API key. They are saved to your account (the browser keeps a copy for the first paint) and sent with every run. If OpenAI rejects the key, the quota runs out or the model is not available, the chat and the canvas explain what to fix.

## Scripts

Run these from the repo root. Turborepo runs them in every package.

| Command            | What it does                                                     |
| ------------------ | ---------------------------------------------------------------- |
| `pnpm dev`         | Starts the web app on port 3000                                  |
| `pnpm build`       | Builds for production                                            |
| `pnpm lint`        | Runs ESLint with zero warnings allowed                           |
| `pnpm check-types` | Type-checks every package                                        |
| `pnpm test`        | Runs the Vitest suites                                           |
| `pnpm format`      | Formats `ts`, `tsx` and `md` files with Prettier                 |
| `pnpm db:migrate`  | Applies the database migrations to `DATABASE_URL`                |
| `pnpm db:generate` | Writes a migration after a change to `packages/db/src/schema.ts` |

Commits go through Husky: lint-staged formats and lints staged files, and commitlint checks for a conventional commit message.

## Architecture

```text
apps/web/                  Next.js app: pages, API routes, the CopilotKit runtime
  app/api/copilotkit/      CopilotRuntime route: Clerk check, thread guard, the agent
  app/api/conversations/   Conversations and their quiz attempts
  app/api/memory/          The Memory panel's API
  app/history/, memory/    Progress page and Memory panel
  features/                canvas, chat, conversations, memory, history, settings, api-key
  components/layout/       App shell, header, workspace, resize handle
apps/agent/                @repo/agent: the LangChain agent, its tools, prompts and memory
packages/db/               @repo/db: drizzle schema, migrations, repositories, checkpointer
packages/shared/           zod schemas, A2UI templates and shared constants
packages/eslint-config/    ESLint presets
packages/typescript-config/ tsconfig presets
```

Everything runs inside the Next.js app. The runtime route checks the Clerk session, then builds the agent for that request: a LangChain.js `createAgent` Supervisor, run in the same process through `@ag-ui/langgraph`'s `LangGraphAgent` and a small client of our own. Each run, the client:

1. Reads the settings and a quiz Submit from `forwardedProps`, and puts them, the verified user id, the app context and the student's long-term memory into the run's context. The OpenAI key stays inside the model instance, so it never reaches a trace.
2. Starts from the conversation's checkpoint and applies only the edits the browser may make (quiz answers, the learning material's text and view). Every other state key the browser sends is ignored.
3. Runs the Supervisor with its subagent tools (`research`, `makeMaterial`, `simplify`, `generateQuiz`, `evaluate`) and its chat and Board tools. Each subagent is one structured-output call that streams a draft to the canvas.
4. Filters the stream to the browser: no raw graph events, only the canvas's state keys, and one snapshot per change.

A few rules keep the flow reliable:

- **The quiz stays sealed.** The answer key is encrypted into state, and no snapshot or delta before Submit contains the correct answers.
- **Submit is graded in code.** The Submit button sends an A2UI action, and the run's first model call is answered by one that only calls `evaluate`. A graded quiz ends the run there; the real model only explains a failed grading.
- **One conversation, one topic.** "New topic" starts a new conversation. Each is a thread whose checkpoint (Postgres) brings back its chat, canvas and Board on reload.
- **Records and memory are written by code.** Each finished stage writes its row (research, material, quiz attempt). A graded attempt updates concept mastery and the topic's scores in the same transaction. After a run, one small model call notes what the student's message says about them (level, style, language), and long threads are folded into a summary that only the agent reads.
- **Failures can be retried.** A failed step sets `status.error`. The canvas shows it with a Retry button, and the Supervisor explains it in chat.

The design is in [docs/design.md](./docs/design.md#v2-langchainjs-agent-clerk-and-postgres), and the migration from v1 in [docs/v2-migration-plan.md](./docs/v2-migration-plan.md).
