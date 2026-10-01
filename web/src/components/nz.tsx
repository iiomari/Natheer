/**
 * Nazeer design-system components built on the tokens in globals.css.
 * Status is never color alone: every chip and card carries a label (and usually an icon).
 */
import Link from "next/link"
import type { LucideIcon } from "lucide-react"
import { AlertTriangle, CheckCircle2, CircleHelp, ShieldCheck, XCircle } from "lucide-react"

import { cn } from "@/lib/utils"

// ---------------------------------------------------------------- brand

export function BrandMark({ className }: { className?: string }) {
  // A simple geometric mark: two offset squares (the record and its twin). No external assets.
  return (
    <svg viewBox="0 0 32 32" aria-hidden="true" className={cn("size-8", className)}>
      <rect x="3" y="3" width="18" height="18" rx="5" fill="var(--primary)" />
      <rect x="11" y="11" width="18" height="18" rx="5" fill="var(--twin)" opacity="0.92" />
      <rect x="11" y="11" width="10" height="10" rx="2" fill="var(--surface)" opacity="0.9" />
    </svg>
  )
}

export function Brand({ href = "/", className }: { href?: string; className?: string }) {
  return (
    <Link href={href} className={cn("inline-flex items-center gap-2.5 rounded-md outline-none focus-visible:ring-3 focus-visible:ring-ring/40", className)}>
      <BrandMark />
      <span className="flex flex-col leading-none">
        <span className="text-xl font-bold text-foreground">نَظير</span>
        <span className="ltr-text mt-1 text-[0.6875rem] font-semibold tracking-[0.18em] text-muted-foreground">NAZEER</span>
      </span>
    </Link>
  )
}

// ---------------------------------------------------------------- bidi helpers

/** Numbers, IDs, IBANs, dates: always shown left-to-right in stored order. */
export function Num({ children, className }: { children: React.ReactNode; className?: string }) {
  return (
    <bdi dir="ltr" className={cn("ltr-num", className)}>
      {children}
    </bdi>
  )
}

/** Latin text (emails, column names) inside Arabic. */
export function Ltr({ children, className }: { children: React.ReactNode; className?: string }) {
  return (
    <bdi dir="ltr" className={cn("ltr-text", className)}>
      {children}
    </bdi>
  )
}

// ---------------------------------------------------------------- page structure

export function PageHeader({
  title,
  description,
  actions,
}: {
  title: string
  description?: React.ReactNode
  actions?: React.ReactNode
}) {
  return (
    <div className="mb-8 flex flex-wrap items-end justify-between gap-4">
      <div className="min-w-0">
        <h1 className="page-title">{title}</h1>
        {description ? <p className="lead mt-2 max-w-2xl">{description}</p> : null}
      </div>
      {actions ? <div className="flex flex-wrap items-center gap-2">{actions}</div> : null}
    </div>
  )
}

export function Section({ title, description, actions, children, className }: {
  title?: string
  description?: React.ReactNode
  actions?: React.ReactNode
  children: React.ReactNode
  className?: string
}) {
  return (
    <section className={cn("space-y-4", className)}>
      {title || actions ? (
        <div className="flex flex-wrap items-end justify-between gap-3">
          <div>
            {title ? <h2 className="section-title">{title}</h2> : null}
            {description ? <p className="mt-1 text-sm text-muted-foreground">{description}</p> : null}
          </div>
          {actions}
        </div>
      ) : null}
      {children}
    </section>
  )
}

// ---------------------------------------------------------------- chips

export type ChipTone = "neutral" | "primary" | "twin" | "sensitive" | "review"

const TONES: Record<ChipTone, string> = {
  neutral: "bg-muted text-muted-foreground border-border",
  primary: "bg-accent text-accent-foreground border-primary/20",
  twin: "bg-twin-soft text-twin border-twin/25",
  sensitive: "bg-sensitive-soft text-sensitive border-sensitive/25",
  review: "bg-review-soft text-review border-review/30",
}

export function Chip({
  tone = "neutral",
  icon: Icon,
  children,
  className,
}: {
  tone?: ChipTone
  icon?: LucideIcon
  children: React.ReactNode
  className?: string
}) {
  return (
    <span
      className={cn(
        "inline-flex h-6 items-center gap-1 rounded-full border px-2.5 text-xs font-semibold whitespace-nowrap",
        TONES[tone],
        className,
      )}
    >
      {Icon ? <Icon className="size-3.5" aria-hidden="true" /> : null}
      {children}
    </span>
  )
}

/** Personal-data type chips used across detection views. */
export const DATA_TYPES = {
  SAUDI_ID: { label: "هوية", tone: "sensitive" },
  IQAMA: { label: "إقامة", tone: "sensitive" },
  MOBILE: { label: "جوال", tone: "sensitive" },
  IBAN: { label: "آيبان", tone: "sensitive" },
  EMAIL: { label: "بريد", tone: "sensitive" },
  PERSON_NAME: { label: "اسم", tone: "sensitive" },
  REVIEW: { label: "للمراجعة", tone: "review" },
  REJECTED: { label: "رُفض", tone: "neutral" },
} as const satisfies Record<string, { label: string; tone: ChipTone }>

export function TypeChip({ type }: { type: keyof typeof DATA_TYPES }) {
  const t = DATA_TYPES[type]
  return <Chip tone={t.tone}>{t.label}</Chip>
}

export function VerdictChip({ verdict }: { verdict: "PASS" | "FAIL" | "PENDING" }) {
  if (verdict === "PASS") return <Chip tone="twin" icon={CheckCircle2}>ناجح</Chip>
  if (verdict === "FAIL") return <Chip tone="sensitive" icon={XCircle}>راسب</Chip>
  return <Chip tone="neutral" icon={CircleHelp}>قيد التحقق</Chip>
}

// ---------------------------------------------------------------- cards

export function StatCard({
  label,
  value,
  hint,
  icon: Icon,
}: {
  label: string
  value: React.ReactNode
  hint?: React.ReactNode
  icon?: LucideIcon
}) {
  return (
    <div className="rounded-xl border border-border bg-card p-5 shadow-card">
      <div className="flex items-center justify-between gap-3">
        <span className="text-sm font-semibold text-muted-foreground">{label}</span>
        {Icon ? (
          <span className="grid size-9 place-items-center rounded-lg bg-accent text-accent-foreground">
            <Icon className="size-4.5" aria-hidden="true" />
          </span>
        ) : null}
      </div>
      <div className="mt-3 text-[2rem] leading-none font-bold">{value}</div>
      {hint ? <div className="mt-2 text-sm text-muted-foreground">{hint}</div> : null}
    </div>
  )
}

export function VerdictCard({
  title,
  verdict,
  value,
  explanation,
}: {
  title: string
  verdict: "PASS" | "FAIL"
  value: React.ReactNode
  explanation: string
}) {
  const pass = verdict === "PASS"
  return (
    <div
      className={cn(
        "rounded-xl border bg-card p-5 shadow-card",
        pass ? "border-twin/30" : "border-sensitive/35",
      )}
    >
      <div className="flex items-start justify-between gap-3">
        <h3 className="text-base font-bold">{title}</h3>
        <VerdictChip verdict={verdict} />
      </div>
      <div className="mt-4 text-[2.25rem] leading-none font-bold">{value}</div>
      <p className="mt-3 text-sm leading-6 text-muted-foreground">{explanation}</p>
    </div>
  )
}

// ---------------------------------------------------------------- states

export function EmptyState({
  icon: Icon = ShieldCheck,
  title,
  description,
  action,
}: {
  icon?: LucideIcon
  title: string
  description?: React.ReactNode
  action?: React.ReactNode
}) {
  return (
    <div className="flex flex-col items-center rounded-xl border border-dashed border-border bg-card px-6 py-14 text-center">
      <span className="grid size-12 place-items-center rounded-xl bg-accent text-accent-foreground">
        <Icon className="size-6" aria-hidden="true" />
      </span>
      <h3 className="mt-4 text-lg font-bold">{title}</h3>
      {description ? <p className="mt-2 max-w-md text-sm leading-6 text-muted-foreground">{description}</p> : null}
      {action ? <div className="mt-6">{action}</div> : null}
    </div>
  )
}

export function InlineError({ children }: { children: React.ReactNode }) {
  return (
    <div role="alert" className="flex items-start gap-2 rounded-lg border border-sensitive/30 bg-sensitive-soft px-3 py-2.5 text-sm text-sensitive">
      <AlertTriangle className="mt-0.5 size-4 shrink-0" aria-hidden="true" />
      <span>{children}</span>
    </div>
  )
}

export function Notice({ tone = "primary", icon: Icon = CircleHelp, children }: {
  tone?: "primary" | "review" | "twin"
  icon?: LucideIcon
  children: React.ReactNode
}) {
  const tones = {
    primary: "border-primary/20 bg-accent text-accent-foreground",
    review: "border-review/30 bg-review-soft text-review",
    twin: "border-twin/25 bg-twin-soft text-twin",
  }
  return (
    <div className={cn("flex items-start gap-2.5 rounded-lg border px-4 py-3 text-sm leading-6", tones[tone])}>
      <Icon className="mt-1 size-4 shrink-0" aria-hidden="true" />
      <div>{children}</div>
    </div>
  )
}

export function Spinner({ className }: { className?: string }) {
  return (
    <span
      role="status"
      aria-label="جارٍ التحميل"
      className={cn("inline-block size-5 animate-spin rounded-full border-2 border-current border-t-transparent", className)}
    />
  )
}
