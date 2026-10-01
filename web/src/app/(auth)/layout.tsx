import Link from "next/link"

import { Brand } from "@/components/nz"
import { ThemeToggle } from "@/components/theme"

export default function AuthLayout({ children }: { children: React.ReactNode }) {
  return (
    <div className="flex min-h-screen flex-col">
      <header className="mx-auto flex h-16 w-full max-w-6xl items-center justify-between px-4 sm:px-6">
        <Brand />
        <ThemeToggle />
      </header>
      <main className="flex flex-1 items-start justify-center px-4 pt-6 pb-16 sm:pt-12">
        <div className="w-full max-w-[28rem]">{children}</div>
      </main>
      <footer className="pb-8 text-center text-xs text-muted-foreground">
        <Link href="/privacy" className="hover:text-foreground">الخصوصية</Link>
        <span className="mx-2">·</span>
        <Link href="/terms" className="hover:text-foreground">الشروط</Link>
      </footer>
    </div>
  )
}
