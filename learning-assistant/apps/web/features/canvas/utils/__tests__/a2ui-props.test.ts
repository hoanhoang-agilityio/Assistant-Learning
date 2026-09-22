import { describe, expect, it } from "vitest";

import {
  readList,
  readMasteryItems,
  readStatTiles,
  readText,
  readTier,
} from "@/features/canvas/utils/a2ui-props";

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

describe("readStatTiles / readMasteryItems", () => {
  it("keeps well-formed items and drops the rest", () => {
    expect(
      readStatTiles([
        { label: "Accuracy", value: "67%", tone: "indigo" },
        { label: "Bad tone", value: "1", tone: "purple" },
        "oops",
      ]),
    ).toEqual([{ label: "Accuracy", value: "67%", tone: "indigo" }]);
    expect(
      readMasteryItems([
        { concept: "Scope", percent: 120, tone: "rose", isWeakest: true },
      ]),
    ).toEqual([]);
  });

  it("falls back to an empty list for an unresolved binding", () => {
    expect(readStatTiles({ path: "/tiles" })).toEqual([]);
  });
});

describe("readTier", () => {
  it("reads a tier name only", () => {
    expect(readTier("Master")).toBe("Master");
    expect(readTier("Expert")).toBeNull();
  });
});
