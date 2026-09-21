/** One component in an A2UI v0.9 `updateComponents` message (flat format). */
export interface SurfaceComponent {
  id: string;
  component: string;
  [prop: string]: unknown;
}

/**
 * A fixed canvas surface: its components never change, and the stage's data
 * reaches them through `{ "path": "/…" }` bindings into the data model.
 */
export interface SurfaceTemplate {
  surfaceId: string;
  catalogId: string;
  components: SurfaceComponent[];
}
