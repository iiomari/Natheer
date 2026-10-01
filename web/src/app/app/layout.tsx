import type { Metadata } from "next"

import { WorkspaceShell } from "@/components/shell"
import { SessionProvider } from "@/lib/session"

export const metadata: Metadata = { title: "مساحة العمل", robots: { index: false, follow: false } }

export default function WorkspaceLayout({ children }: { children: React.ReactNode }) {
  return (
    <SessionProvider>
      <WorkspaceShell>{children}</WorkspaceShell>
    </SessionProvider>
  )
}
