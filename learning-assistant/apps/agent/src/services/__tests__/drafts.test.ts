import { describe, expect, it, vi } from "vitest";

import { DRAFT_INTERVAL_MS } from "../../constants/agents";
import { throttleDrafts } from "../drafts";

describe("throttleDrafts", () => {
  it("drops calls closer together than the interval", () => {
    let time = 0;
    const fn = vi.fn();
    const report = throttleDrafts(fn, () => time);

    report(1);
    time += DRAFT_INTERVAL_MS - 1;
    report(2);
    time += 1;
    report(3);

    expect(fn.mock.calls).toEqual([[1], [3]]);
  });
});
