"use client"

import Link from "next/link"
import { useSearchParams } from "next/navigation"
import { Suspense } from "react"
import { CheckCircle2, Circle, Database, FileCheck2, Share2, Undo2 } from "lucide-react"

import { useCurrentMembership } from "@/components/org"
import { Chip, Notice, PageHeader, Section, StatCard } from "@/components/nz"
import { buttonVariants } from "@/components/ui/button"
import { VerdictChip } from "@/components/nz"
import { formatDateTime, useApi } from "@/lib/use-api"

type Stats = {
  datasets: number
  twins: number
  active_shares: number
  pending_returns: number
  storage_mb: number
  recent_twins: { id: string; dataset_name: string; mode: string; verdict: "PASS" | "FAIL"; created_at: string }[]
}
import { cn } from "@/lib/utils"

function Step({ done, title, text, href, soon }: { done: boolean; title: string; text: string; href?: string; soon?: boolean }) {
  return (
    <li className="flex items-start gap-4 px-6 py-4">
      {done ? (
        <CheckCircle2 className="mt-0.5 size-5 shrink-0 text-twin" aria-label="مكتمل" />
      ) : (
        <Circle className="mt-0.5 size-5 shrink-0 text-muted-foreground" aria-label="غير مكتمل" />
      )}
      <div className="min-w-0 flex-1">
        <p className={cn("font-bold", done && "text-muted-foreground line-through")}>{title}</p>
        <p className="mt-0.5 text-sm text-muted-foreground">{text}</p>
      </div>
      {soon ? (
        <Chip>قريباً</Chip>
      ) : href && !done ? (
        <Link href={href} className={buttonVariants({ size: "sm", variant: "outline" })}>ابدأ</Link>
      ) : null}
    </li>
  )
}

function Dashboard() {
  const { orgId, membership } = useCurrentMembership()
  const welcome = useSearchParams().get("welcome")
  const isAdmin = membership?.role === "admin"
  const canManage = isAdmin || membership?.data_manager
  const members = useApi<{ id: string }[]>(canManage ? `/orgs/${orgId}/members` : null)
  const stats = useApi<Stats>(`/orgs/${orgId}/stats`)

  if (!membership) return null
  const teamInvited = (members.data?.length ?? 0) > 1
  const st = stats.data

  return (
    <>
      <PageHeader title="لوحة المعلومات" description={membership.org_name} />
      {welcome ? (
        <div className="mb-8">
          <Notice tone="twin" icon={CheckCircle2}>
            أُنشئت مساحة منشأتك. ابدأ برفع بيانات تجريبية، أو ادعُ فريقك برابط تنسخه وترسله.
          </Notice>
        </div>
      ) : null}

      <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
        <StatCard label="مجموعات البيانات" value={st?.datasets ?? "—"} icon={Database} hint={st ? <>التخزين: {st.storage_mb} م.ب من 100</> : undefined} />
        <StatCard label="النظائر" value={st?.twins ?? "—"} icon={FileCheck2} />
        <StatCard label="المشاركات النشطة" value={st?.active_shares ?? "—"} icon={Share2} />
        <StatCard label="مرتجعات بانتظار المراجعة" value={st?.pending_returns ?? "—"} icon={Undo2} hint="تُتاح في الإصدار القادم" />
      </div>

      {canManage ? (
        <>
        <Section title="البدء" description="خطوات العمل في مساحة منشأتك." className="mt-10">
          <ol className="divide-y divide-border rounded-xl border border-border bg-card shadow-card">
            {isAdmin ? <Step done={teamInvited} title="دعوة فريقك" text="أنشئ رابط دعوة وأرسله للموظف بنفسك." href={`/app/o/${orgId}/team`} /> : null}
            <Step done={(st?.datasets ?? 0) > 0} title="رفع أول مجموعة بيانات" text="CSV أو Excel؛ يُكتشف الترميز والفواصل والعناوين تلقائياً." href={`/app/o/${orgId}/datasets`} />
            <Step done={(st?.twins ?? 0) > 0} title="مراجعة الكشف وتوليد النظير" text="راجع ما اكتُشف ثم ولّد نظيراً مقنّعاً." href={`/app/o/${orgId}/datasets`} />
            <Step done={(st?.active_shares ?? 0) > 0} title="مشاركة نظير ناجح" text="مع أعضاء المنشأة أو برابط لمستلم خارجي." href={`/app/o/${orgId}/datasets`} />
          </ol>
        </Section>
        {st?.recent_twins.length ? (
          <Section title="آخر النظائر" className="mt-10">
            <ul className="divide-y divide-border rounded-xl border border-border bg-card shadow-card">
              {st.recent_twins.map((t) => (
                <li key={t.id}>
                  <Link href={`/app/o/${orgId}/twins/${t.id}`} className="flex flex-wrap items-center justify-between gap-3 px-5 py-4 hover:bg-muted/50">
                    <span className="font-semibold">{t.dataset_name}<span className="ms-3 text-sm font-normal text-muted-foreground">{formatDateTime(t.created_at)}</span></span>
                    <VerdictChip verdict={t.verdict} />
                  </Link>
                </li>
              ))}
            </ul>
          </Section>
        ) : null}
        </>
      ) : (
        <div className="mt-10">
          <Notice>
            البيانات التي تشاركها معك منشأتك تظهر في{" "}
            <Link href="/app/received" className="font-bold underline">البيانات المستلمة</Link>.
          </Notice>
        </div>
      )}
    </>
  )
}

export default function DashboardPage() {
  return (
    <Suspense>
      <Dashboard />
    </Suspense>
  )
}
