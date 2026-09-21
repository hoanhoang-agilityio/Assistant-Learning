/**
 * The binder resolves `{ path }` bindings before a component renders, but the
 * catalog's prop types still include the unresolved binding. These narrow a
 * resolved prop to what the component draws, with an empty fallback.
 */
export const readText = (value: unknown): string =>
  typeof value === "string" ? value : "";

export const readList = <T>(value: readonly T[] | object | undefined): T[] =>
  Array.isArray(value) ? value : [];
