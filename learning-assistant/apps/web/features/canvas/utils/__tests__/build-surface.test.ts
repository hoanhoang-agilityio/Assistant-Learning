import { extendsBasicCatalog } from "@copilotkit/a2ui-renderer";
import { ROOT_COMPONENT_ID } from "@repo/shared/a2ui/canvas-catalog";
import { RESEARCH_TEMPLATE } from "@repo/shared/a2ui/templates";
import type { ResearchResult } from "@repo/shared/schemas";
import { describe, expect, it } from "vitest";

import { CANVAS_CATALOG } from "@/features/canvas/constants/a2ui-catalog";
import {
  buildSurface,
  createResearchDataModel,
} from "@/features/canvas/utils/build-surface";

const research: ResearchResult = {
  title: "Photosynthesis",
  summary: "Plants turn light into chemical energy.",
  keyInsight: "Light energy is stored as sugar.",
  keyTerms: [{ term: "Chlorophyll", definition: "The green pigment." }],
  sources: [{ title: "Wikipedia", url: "https://en.wikipedia.org/wiki/P" }],
};

/** Every `{ "path": … }` binding anywhere in a value. */
const collectBindingPaths = (value: unknown): string[] => {
  if (Array.isArray(value)) return value.flatMap(collectBindingPaths);
  if (!value || typeof value !== "object") return [];
  if ("path" in value && typeof value.path === "string") return [value.path];
  return Object.values(value).flatMap(collectBindingPaths);
};

/** Resolves a JSON Pointer such as `/research/title`. */
const resolvePointer = (data: unknown, pointer: string): unknown =>
  pointer
    .split("/")
    .slice(1)
    .reduce<unknown>(
      (node, key) =>
        node && typeof node === "object"
          ? (node as Record<string, unknown>)[key]
          : undefined,
      data,
    );

describe("buildSurface", () => {
  const messages = buildSurface(
    RESEARCH_TEMPLATE,
    createResearchDataModel(research),
  );

  it("creates the surface, then its components, then its data", () => {
    expect(messages.map((message) => Object.keys(message)[1])).toEqual([
      "createSurface",
      "updateComponents",
      "updateDataModel",
    ]);
    expect(messages.every(({ version }) => version === "v0.9")).toBe(true);
  });

  it("uses the template's surface and catalog ids", () => {
    expect(messages[0]).toEqual({
      version: "v0.9",
      createSurface: {
        surfaceId: RESEARCH_TEMPLATE.surfaceId,
        catalogId: CANVAS_CATALOG.id,
      },
    });
  });

  it("binds every template path to research data", () => {
    const dataModel = createResearchDataModel(research);
    const paths = collectBindingPaths(RESEARCH_TEMPLATE.components);

    expect(paths).toEqual([
      "/research/title",
      "/research/summary",
      "/research/keyInsight",
      "/research/keyTerms",
      "/research/sources",
    ]);
    for (const path of paths) {
      expect(resolvePointer(dataModel, path), path).toBeDefined();
    }
    expect(resolvePointer(dataModel, "/research/keyTerms")).toBe(
      research.keyTerms,
    );
  });
});

describe("research template", () => {
  const ids = RESEARCH_TEMPLATE.components.map(({ id }) => id);

  it("has a root and unique component ids", () => {
    expect(ids).toContain(ROOT_COMPONENT_ID);
    expect(new Set(ids).size).toBe(ids.length);
  });

  it("only uses components from the canvas catalog", () => {
    for (const { component } of RESEARCH_TEMPLATE.components) {
      expect(CANVAS_CATALOG.components.has(component), component).toBe(true);
    }
  });

  it("only refers to child ids that exist", () => {
    const childIds = RESEARCH_TEMPLATE.components.flatMap((component) => [
      ...(Array.isArray(component.children) ? component.children : []),
      ...(typeof component.child === "string" ? [component.child] : []),
    ]);
    for (const id of childIds) expect(ids).toContain(id);
  });
});

describe("CANVAS_CATALOG", () => {
  it("extends the basic catalog", () => {
    expect(extendsBasicCatalog(CANVAS_CATALOG)).toBe(true);
  });
});
