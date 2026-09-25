import { describe, expect, it } from "vitest";

import { getSurfaceComponents } from "../board-surface";

const surface = (operations: unknown[]) => ({
  id: "board-1",
  title: "View",
  operations,
  revision: 1,
});

describe("getSurfaceComponents", () => {
  it("returns the components of the updateComponents operation", () => {
    const components = [{ id: "root", component: "Stack", children: [] }];
    expect(
      getSurfaceComponents(
        surface([
          { version: "v0.9", createSurface: { surfaceId: "board-1" } },
          {
            version: "v0.9",
            updateComponents: { surfaceId: "board-1", components },
          },
        ]),
      ),
    ).toEqual(components);
  });

  it("returns null when no operation carries components", () => {
    expect(
      getSurfaceComponents(
        surface([{ version: "v0.9", createSurface: { surfaceId: "board-1" } }]),
      ),
    ).toBeNull();
  });
});
