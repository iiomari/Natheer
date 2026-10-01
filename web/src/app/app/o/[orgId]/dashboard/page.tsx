"use client"

import Link from "next/link"
import { useSearchParams } from "next/navigation"
import { Suspense } from "react"
import { CheckCircle2, Circle, Database, FileCheck2, Share2, Undo2 } from "lucide-react"

import { useCurrentMembership } from "@/components/org"
import { Chip, Notice, PageHeader, Section, StatCard } from "@/components/nz"
import { buttonVariants } from "@/components/ui/button"
import { useSession } from "@/lib/session"
import type { Member } from "@/lib/types"
import { useApi } from "@/lib/use-api"
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
  const { me } = useSession()
  const { orgId, membership } = useCurrentMembership()
  const welcome = useSearchParams().get("welcome")
  const isAdmin = membership?.role === "admin"
  const members = useApi<Member[]>(isAdmin ? `/orgs/${orgId}/members` : null)

  if (!membership) return null
  const teamInvited = (members.data?.length ?? 0) > 1

  return (
    <>
      <PageHeader title="لوحة المعلومات" description={membership.org_name} />
      {welcome ? (
        <div className="mb-8">
          <Notice tone="twin" icon={CheckCircle2}>
            أُنشئ حسابك. أرسلنا رابط تأكيد إلى بريدك؛ أكّده لتتمكن من استلام البيانات المشاركة معك.
          </Notice>
        </div>
      ) : null}

      <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
        <StatCard label="مجموعات البيانات" value="0" icon={Database} hint="لم تُرفع بيانات بعد" />
        <StatCard label="النظائر" value="0" icon={FileCheck2} hint="تُولَّد بعد الرفع والمراجعة" />
        <StatCard label="المشاركات النشطة" value="0" icon={Share2} hint="لا مشاركات بعد" />
        <StatCard label="مرتجعات بانتظار المراجعة" value="0" icon={Undo2} hint="لا مرتجعات بعد" />
      </div>

      {isAdmin ? (
        <Section title="البدء" description="خطوات إعداد مساحة منشأتك." className="mt-10">
          <ol className="divide-y divide-border rounded-xl border border-border bg-card shadow-card">
            <Step done={Boolean(me?.email_verified)} title="تأكيد البريد الإلكتروني" text="مطلوب قبل استلام أي بيانات مشاركة." />
            <Step done={teamInvited} title="دعوة فريقك" text="أضف الموظفين الذين سيستلمون النظائر أو يديرون البيانات." href={`/app/o/${orgId}/team`} />
            <Step done={false} title="رفع أول مجموعة بيانات" text="ملفات CSV أو Excel أو اتصال MySQL للقراءة فقط." soon />
            <Step done={false} title="توليد نظير ومشاركته" text="بعد مراجعة الكشف، ولّد النظير وشاركه إن كانت نتيجته ناجحة." soon />
          </ol>
        </Section>
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
