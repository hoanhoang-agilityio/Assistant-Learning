"use client";

import { Component, type ErrorInfo, type ReactNode } from "react";

export interface SurfaceBoundaryProps {
  /** Shown instead of the surface once a component in it throws. */
  fallback: ReactNode;
  children: ReactNode;
}

interface SurfaceBoundaryState {
  hasError: boolean;
}

/**
 * Catches a render error in an A2UI surface, so one bad component shows the
 * fallback instead of blanking the canvas. React only catches render errors
 * in a class component, so this is the one class in the app. Remount it (by
 * `key`) to try a new surface.
 */
export class SurfaceBoundary extends Component<
  SurfaceBoundaryProps,
  SurfaceBoundaryState
> {
  state: SurfaceBoundaryState = { hasError: false };

  static getDerivedStateFromError = (): SurfaceBoundaryState => ({
    hasError: true,
  });

  componentDidCatch = (error: Error, info: ErrorInfo) => {
    console.error("[canvas] A surface failed to render", error, info);
  };

  render = () =>
    this.state.hasError ? this.props.fallback : this.props.children;
}
