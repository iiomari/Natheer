"use client"

import Link from "next/link"
import { useParams, usePathname, useRouter } from "next/navigation"
import { useState } from "react"
import type { LucideIcon } from "lucide-react"
import {
  Building2,
  ChevronsUpDown,
  Database,
  Inbox,
  LayoutDashboard,
  LogOut,
  Menu,
  ScrollText,
  Settings,
  Share2,
  Undo2,
  Users,
} from "lucide-react"

import { Brand, Chip, Ltr, Spinner } from "@/components/nz"
import { ThemeToggle } from "@/components/theme"
import { Button } from "@/components/ui/button"
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuGroup,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu"
import { Sheet, SheetContent, SheetTitle, SheetTrigger } from "@/components/ui/sheet"
import { useSession } from "@/lib/session"
import type { MembershipRef } from "@/lib/types"
import { cn } from "@/lib/utils"

type NavItem = { href: string; label: string; icon: LucideIcon; soon?: boolean }

function orgNav(m: MembershipRef): { title: string; items: NavItem[] }[] {
  const base = `/app/o/${m.org_id}`
  const groups: { title: string; items: NavItem[] }[] = []
  const work: NavItem[] = [{ href: `${base}/dashboard`, label: "لوحة المعلومات", icon: LayoutDashboard }]
  if (m.role === "admin" || m.data_manager) {
    work.push(
      { href: `${base}/datasets`, label: "مجموعات البيانات", icon: Database },
      { href: `${base}/shares`, label: "المشاركات", icon: Share2 },
      { href: `${base}/returns`, label: "المرتجعات", icon: Undo2 },
    )
  }
  groups.push({ title: "المنشأة", items: work })
  if (m.role === "admin") {
    groups.push({
      title: "الإدارة",
      items: [
        { href: `${base}/team`, label: "الفريق", icon: Users },
        { href: `${base}/audit`, label: "سجل التدقيق", icon: ScrollText },
        { href: `${base}/settings`, label: "الإعدادات", icon: Settings },
      ],
    })
  }
  return groups
}

const PERSONAL: NavItem[] = [{ href: "/app/received", label: "البيانات المستلمة", icon: Inbox }]

function NavLinks({ onNavigate }: { onNavigate?: () => void }) {
  const { me } = useSession()
  const pathname = usePathname()
  const params = useParams<{ orgId?: string }>()
  const current = me?.memberships.find((m) => m.org_id === params.orgId) ?? me?.memberships[0]
  const groups = [...(current ? orgNav(current) : []), { title: "مساحتي", items: PERSONAL }]

  return (
    <nav aria-label="تنقّل مساحة العمل" className="space-y-6">
      {groups.map((g) => (
        <div key={g.title}>
          <p className="px-3 pb-2 text-xs font-bold tracking-wide text-muted-foreground">{g.title}</p>
          <ul className="space-y-0.5">
            {g.items.map((item) => {
              const active = pathname === item.href || pathname.startsWith(`${item.href}/`)
              return (
                <li key={item.href}>
                  <Link
                    href={item.href}
                    onClick={onNavigate}
                    aria-current={active ? "page" : undefined}
                    className={cn(
                      "flex h-10 items-center gap-3 rounded-lg px-3 text-[0.9375rem] font-medium transition-colors",
                      active
                        ? "bg-sidebar-accent font-bold text-sidebar-accent-foreground"
                        : "text-muted-foreground hover:bg-muted hover:text-foreground",
                    )}
                  >
                    <item.icon className="size-4.5 shrink-0" aria-hidden="true" />
                    <span className="flex-1 truncate">{item.label}</span>
                    {item.soon ? <span className="text-[0.6875rem] font-semibold text-muted-foreground">قريباً</span> : null}
                  </Link>
                </li>
              )
            })}
          </ul>
        </div>
      ))}
    </nav>
  )
}

function OrgSwitcher() {
  const { me } = useSession()
  const router = useRouter()
  const params = useParams<{ orgId?: string }>()
  if (!me || me.memberships.length === 0) return null
  const current = me.memberships.find((m) => m.org_id === params.orgId) ?? me.memberships[0]
  const roleLabel = current.role === "admin" ? "مدير" : current.data_manager ? "مدير بيانات" : "عضو"
  const box = (
    <span className="flex w-full items-center gap-3 rounded-lg border border-border bg-surface px-3 py-2.5 text-start">
      <span className="grid size-9 shrink-0 place-items-center rounded-lg bg-accent text-accent-foreground">
        <Building2 className="size-4.5" aria-hidden="true" />
      </span>
      <span className="min-w-0 flex-1">
        <span className="block truncate text-sm font-bold">{current.org_name}</span>
        <span className="block text-xs text-muted-foreground">{roleLabel}</span>
      </span>
      {me.memberships.length > 1 ? <ChevronsUpDown className="size-4 text-muted-foreground" aria-hidden="true" /> : null}
    </span>
  )
  if (me.memberships.length === 1) return box
  return (
    <DropdownMenu>
      <DropdownMenuTrigger className="w-full rounded-lg outline-none focus-visible:ring-3 focus-visible:ring-ring/40">{box}</DropdownMenuTrigger>
      <DropdownMenuContent className="w-60">
        <DropdownMenuGroup>
          <DropdownMenuLabel>المنشآت</DropdownMenuLabel>
          {me.memberships.map((m) => (
            <DropdownMenuItem key={m.org_id} onClick={() => router.push(`/app/o/${m.org_id}/dashboard`)}>
              <Building2 /> {m.org_name}
            </DropdownMenuItem>
          ))}
        </DropdownMenuGroup>
      </DropdownMenuContent>
    </DropdownMenu>
  )
}

function UserMenu() {
  const { me, logout } = useSession()
  if (!me) return null
  const initials = me.full_name.trim().split(/\s+/).slice(0, 2).map((w) => w[0]).join("")
  return (
    <DropdownMenu>
      <DropdownMenuTrigger
        render={<Button variant="ghost" className="h-10 gap-2.5 px-2" aria-label="قائمة الحساب" />}
      >
        <span className="grid size-8 place-items-center rounded-full bg-primary text-sm font-bold text-primary-foreground">{initials}</span>
        <span className="hidden max-w-40 truncate text-sm font-semibold sm:block">{me.full_name}</span>
      </DropdownMenuTrigger>
      <DropdownMenuContent align="end" className="w-64">
        <DropdownMenuGroup>
          <DropdownMenuLabel>
            <span className="block truncate text-sm font-bold text-foreground">{me.full_name}</span>
            <Ltr className="block truncate text-xs font-normal text-muted-foreground">{me.email}</Ltr>
          </DropdownMenuLabel>
        </DropdownMenuGroup>
        <DropdownMenuSeparator />
        <DropdownMenuItem variant="destructive" onClick={() => void logout()}>
          <LogOut /> تسجيل الخروج
        </DropdownMenuItem>
      </DropdownMenuContent>
    </DropdownMenu>
  )
}

export function WorkspaceShell({ children }: { children: React.ReactNode }) {
  const { me, loading } = useSession()
  const [open, setOpen] = useState(false)

  const sidebar = (
    <div className="flex h-full flex-col gap-6 p-4">
      <div className="px-2 pt-1">
        <Brand href="/app" />
      </div>
      <OrgSwitcher />
      <div className="min-h-0 flex-1 overflow-y-auto">
        <NavLinks onNavigate={() => setOpen(false)} />
      </div>
      <div className="rounded-lg bg-muted px-3 py-2.5 text-xs leading-5 text-muted-foreground">
        نسخة تجريبية مستضافة. استخدم بيانات تجريبية فقط.
      </div>
    </div>
  )

  return (
    <div className="min-h-screen">
      <aside className="fixed inset-y-0 start-0 z-30 hidden w-[17rem] border-e border-sidebar-border bg-sidebar lg:block">
        {sidebar}
      </aside>
      <div className="lg:ms-[17rem]">
        <header className="sticky top-0 z-20 flex h-16 items-center justify-between gap-4 border-b border-border bg-surface/95 px-4 backdrop-blur sm:px-6">
          <div className="flex items-center gap-2">
            <Sheet open={open} onOpenChange={setOpen}>
              <SheetTrigger render={<Button variant="ghost" size="icon" className="lg:hidden" aria-label="فتح القائمة" />}>
                <Menu />
              </SheetTrigger>
              <SheetContent side="right" className="w-[17rem] p-0">
                <SheetTitle className="sr-only">القائمة</SheetTitle>
                {sidebar}
              </SheetContent>
            </Sheet>
            {me && me.memberships.length === 0 ? <Chip tone="primary">حساب فرد</Chip> : null}
          </div>
          <div className="flex items-center gap-1">
            <ThemeToggle />
            <UserMenu />
          </div>
        </header>
        <main className="mx-auto max-w-6xl px-4 py-8 sm:px-6 lg:py-10">
          {loading || !me ? (
            <div className="flex items-center gap-3 py-20 text-muted-foreground">
              <Spinner className="size-4" /> جارٍ التحميل…
            </div>
          ) : (
            children
          )}
        </main>
      </div>
    </div>
  )
}
