import type {
  Evaluation,
  Feedback,
  LearningLevel,
  QuizQuestion,
  ResearchResult,
  Source,
  Stage,
  Theme,
  Tier,
} from "@repo/shared/schemas";
import type {
  AttemptStatus,
  StoredConversationStatus,
} from "@repo/shared/schemas/conversations";
import {
  boolean,
  index,
  integer,
  jsonb,
  pgTable,
  text,
  timestamp,
  uniqueIndex,
  uuid,
} from "drizzle-orm/pg-core";
import { v4 as uuidv4 } from "uuid";

const createdAt = () =>
  timestamp("created_at", { withTimezone: true }).notNull().defaultNow();

const updatedAt = () =>
  timestamp("updated_at", { withTimezone: true }).notNull().defaultNow();

/** A Clerk user, created on their first request. Deleting one deletes everything below. */
export const users = pgTable("users", {
  id: uuid("id").primaryKey().$defaultFn(uuidv4),
  clerkUserId: text("clerk_user_id").notNull().unique(),
  email: text("email"),
  createdAt: createdAt(),
});

/** What the settings popover sets; the browser keeps a copy for first paint. */
export const userSettings = pgTable("user_settings", {
  userId: uuid("user_id")
    .primaryKey()
    .references(() => users.id, { onDelete: "cascade" }),
  questionCount: integer("question_count").notNull(),
  learningLevel: text("learning_level").$type<LearningLevel>().notNull(),
  theme: text("theme").$type<Theme>().notNull(),
  updatedAt: updatedAt(),
});

/**
 * One topic, one chat thread: `id` is the thread id of its checkpoints.
 * `title` stays empty until the first run; `isTitleCustom` stops the
 * research title from replacing a name the student gave it.
 */
export const conversations = pgTable(
  "conversations",
  {
    id: uuid("id").primaryKey().$defaultFn(uuidv4),
    userId: uuid("user_id")
      .notNull()
      .references(() => users.id, { onDelete: "cascade" }),
    title: text("title"),
    isTitleCustom: boolean("is_title_custom").notNull().default(false),
    topic: text("topic"),
    stage: text("stage").$type<Stage>().notNull().default("idle"),
    status: text("status")
      .$type<StoredConversationStatus>()
      .notNull()
      .default("active"),
    lastActivityAt: timestamp("last_activity_at", { withTimezone: true })
      .notNull()
      .defaultNow(),
    createdAt: createdAt(),
  },
  (table) => [
    index("conversations_user_activity_idx").on(
      table.userId,
      table.lastActivityAt,
    ),
  ],
);

/** The research the Research Agent wrote, as it was saved. */
export const research = pgTable("research", {
  conversationId: uuid("conversation_id")
    .primaryKey()
    .references(() => conversations.id, { onDelete: "cascade" }),
  payload: jsonb("payload").$type<ResearchResult>().notNull(),
  sources: jsonb("sources").$type<Source[]>().notNull(),
  updatedAt: updatedAt(),
});

/** The learning material as the Material and Simplify agents last wrote it. */
export const material = pgTable("material", {
  conversationId: uuid("conversation_id")
    .primaryKey()
    .references(() => conversations.id, { onDelete: "cascade" }),
  original: text("original").notNull(),
  simplified: text("simplified"),
  updatedAt: updatedAt(),
});

/**
 * One go at a quiz. A new quiz starts an attempt; a retake of the same quiz
 * (`quizId`) is a new attempt too. `answerKey` stays sealed.
 */
export const quizAttempts = pgTable(
  "quiz_attempts",
  {
    id: uuid("id").primaryKey().$defaultFn(uuidv4),
    conversationId: uuid("conversation_id")
      .notNull()
      .references(() => conversations.id, { onDelete: "cascade" }),
    quizId: text("quiz_id").notNull(),
    attemptNo: integer("attempt_no").notNull(),
    questions: jsonb("questions").$type<QuizQuestion[]>().notNull(),
    answerKey: text("answer_key").notNull(),
    answers: jsonb("answers").$type<Record<string, number>>().notNull(),
    status: text("status").$type<AttemptStatus>().notNull(),
    scorePct: integer("score_pct"),
    tier: text("tier").$type<Tier>(),
    mastery: jsonb("mastery").$type<Evaluation["mastery"]>(),
    feedback: jsonb("feedback").$type<Feedback>(),
    startedAt: timestamp("started_at", { withTimezone: true })
      .notNull()
      .defaultNow(),
    submittedAt: timestamp("submitted_at", { withTimezone: true }),
  },
  (table) => [
    uniqueIndex("quiz_attempts_conversation_attempt_idx").on(
      table.conversationId,
      table.attemptNo,
    ),
  ],
);

/** The student's rating and note after the feedback. */
export const reflections = pgTable("reflections", {
  id: uuid("id").primaryKey().$defaultFn(uuidv4),
  conversationId: uuid("conversation_id")
    .notNull()
    .references(() => conversations.id, { onDelete: "cascade" }),
  attemptId: uuid("attempt_id").references(() => quizAttempts.id, {
    onDelete: "cascade",
  }),
  rating: integer("rating").notNull(),
  text: text("text").notNull(),
  createdAt: createdAt(),
});
