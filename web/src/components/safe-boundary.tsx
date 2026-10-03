"use client"

import { Component, type ReactNode } from "react"

/** One broken item must never take the whole page down: it shows a short Arabic line instead. */
export class SafeBoundary extends Component<{ children: ReactNode; fallback?: ReactNode }, { failed: boolean }> {
  state = { failed: false }

  static getDerivedStateFromError() {
    return { failed: true }
  }

  componentDidCatch() {
    // no values are logged; the browser console already has the stack for developers
  }

  render() {
    if (this.state.failed)
      return this.props.fallback ?? (
        <p className="rounded-lg border border-border bg-muted/40 px-4 py-3 text-sm text-muted-foreground">تعذّر عرض هذا العنصر.</p>
      )
    return this.props.children
  }
}
