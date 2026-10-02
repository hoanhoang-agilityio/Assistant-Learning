import type { GradedAttempt, TopicHistory } from "@repo/shared/schemas";
import { describe, expect, it } from "vitest";

import {
  calculateScoreTrend,
  formatAttemptDate,
  formatScoreChange,
  summarizeTopic,
} from "@/features/history/utils/score-trend";

const FRAME = {
  width: 140,
  height: 120,
  padding: { top: 10, right: 20, bottom: 10, left: 20 },
};

const attempt = (attemptNo: number, percent: number): GradedAttempt => ({
  attemptNo,
  score: { percent, tier: "Practitioner" },
  submittedAt: `2026-10-0${attemptNo}T10:00:00.000Z`,
});

const topic = (...percents: number[]): TopicHistory => ({
  conversationId: "8c3c5d0e-4f43-4c39-9a51-6f1f0a2b9c11",
  title: "Closures",
  attempts: percents.map((percent, index) => attempt(index + 1, percent)),
  mastery: [],
});

describe("calculateScoreTrend", () => {
  it("spreads attempts across the plot in order, 100% at the top", () => {
    const { points, path } = calculateScoreTrend(
      [attempt(1, 0), attempt(2, 50), attempt(3, 100)],
      FRAME,
    );

    expect(points.map(({ x, y }) => [x, y])).toEqual([
      [20, 110],
      [70, 60],
      [120, 10],
    ]);
    expect(path).toBe("M20 110 L70 60 L120 10");
  });

  it("puts a single attempt in the middle, with no line", () => {
    const { points, path } = calculateScoreTrend([attempt(1, 75)], FRAME);

    expect(points.map(({ x, y }) => [x, y])).toEqual([[70, 35]]);
    expect(path).toBe("");
  });

  it("draws grid lines at 0, 50 and 100%", () => {
    expect(calculateScoreTrend([], FRAME).gridLines).toEqual([
      { percent: 0, y: 110 },
      { percent: 50, y: 60 },
      { percent: 100, y: 10 },
    ]);
  });

  it("keeps the attempt's number and date on its point", () => {
    expect(
      calculateScoreTrend([attempt(2, 40)], FRAME).points[0],
    ).toMatchObject({
      attemptNo: 2,
      percent: 40,
      submittedAt: "2026-10-02T10:00:00.000Z",
    });
  });
});

describe("summarizeTopic", () => {
  it("gives the latest, the best and the change since the first try", () => {
    expect(summarizeTopic(topic(40, 90, 75))).toEqual({
      latestPercent: 75,
      bestPercent: 90,
      change: 35,
    });
  });

  it("has no change with one attempt", () => {
    expect(summarizeTopic(topic(60))).toEqual({
      latestPercent: 60,
      bestPercent: 60,
      change: null,
    });
  });
});

describe("formatScoreChange", () => {
  it.each([
    [35, "+35"],
    [-10, "−10"],
    [0, "±0"],
  ])("writes %d as %s", (change, text) => {
    expect(formatScoreChange(change)).toBe(text);
  });
});

describe("formatAttemptDate", () => {
  it("writes the UTC day", () => {
    expect(formatAttemptDate("2026-10-02T23:30:00.000Z")).toBe("Oct 2");
  });
});
