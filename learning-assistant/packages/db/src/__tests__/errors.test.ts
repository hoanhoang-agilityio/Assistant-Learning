import { describe, expect, it } from "vitest";

import { MISSING_DATABASE_URL_ERROR } from "../constants";
import { isDatabaseUnavailableError } from "../errors";

const withCode = (code: string, message = "failed") =>
  Object.assign(new Error(message), { code });

describe("isDatabaseUnavailableError", () => {
  it.each([
    ["an unknown host", withCode("ENOTFOUND")],
    ["a refused connection", withCode("ECONNREFUSED")],
    ["a missing table", withCode("42P01")],
    ["a missing column", withCode("42703")],
    ["bad credentials", withCode("28P01")],
    ["a connection exception", withCode("08006")],
    ["a missing DATABASE_URL", new Error(MISSING_DATABASE_URL_ERROR)],
    ["a dropped connection", new Error("Connection terminated unexpectedly")],
  ])("is true for %s", (_name, error) => {
    expect(isDatabaseUnavailableError(error)).toBe(true);
  });

  it("finds the driver's error under Drizzle's wrapper", () => {
    const wrapped = new Error("Failed query", { cause: withCode("42P01") });

    expect(isDatabaseUnavailableError(wrapped)).toBe(true);
  });

  it.each([
    ["a unique violation", withCode("23505")],
    ["a plain error", new Error("boom")],
    ["a value that is not an error", "ENOTFOUND"],
    ["nothing", undefined],
  ])("is false for %s", (_name, error) => {
    expect(isDatabaseUnavailableError(error)).toBe(false);
  });
});
