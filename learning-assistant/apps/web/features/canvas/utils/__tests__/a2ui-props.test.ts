import { describe, expect, it } from "vitest";

import { readList, readText } from "@/features/canvas/utils/a2ui-props";

describe("readText", () => {
  it("keeps a resolved string", () => {
    expect(readText("Photosynthesis")).toBe("Photosynthesis");
  });

  it.each([undefined, { path: "/research/title" }, 3])(
    "falls back to an empty string for %s",
    (value) => {
      expect(readText(value)).toBe("");
    },
  );
});

describe("readList", () => {
  it("keeps a resolved array", () => {
    const terms = [{ term: "Chlorophyll", definition: "A pigment." }];
    expect(readList(terms)).toBe(terms);
  });

  it.each([undefined, { path: "/research/keyTerms" }])(
    "falls back to an empty list for %s",
    (value) => {
      expect(readList(value)).toEqual([]);
    },
  );
});
