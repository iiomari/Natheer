"use client"

import Link from "next/link"
import { useParams, useRouter } from "next/navigation"
import { useState } from "react"
import { ArrowRight, CheckCircle2, Download, KeyRound, Share2, ShieldAlert, Sparkles, Table2, XCircle } from "lucide-react"
import { toast } from "sonner"

import { RULE_LABEL } from "@/components/cleaning"
import { DataTable } from "@/components/data"
import { LoadError, Loading, useCurrentMembership } from "@/components/org"
import { Chip, InfoTip, Num, PageHeader, Spinner, VerdictCard, VerdictChip } from "@/components/nz"
import { ShareDialog } from "@/components/share-dialog"
import { Button, buttonVariants } from "@/components/ui/button"
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table"
import { api, messageFor } from "@/lib/api"
import { KIND_AR, checkDetail, checkName } from "@/lib/labels"
import type { Twin } from "@/lib/types"
import { formatDateTime, useApi } from "@/lib/use-api"
import { cn } from "@/lib/utils"

type Preview = { tables: { table: string; columns: string[]; rows: Record<string, [string, string, boolean]>[] }[] }

const STATUS: Record<string, { label: string; tone: "twin" | "sensitive" | "neutral" }> = {
  PASS: { label: "ناجح", tone: "twin" },
  FAIL: { label: "راسب", tone: "sensitive" },
  INFO: { label: "معلومة", tone: "neutral" },
  NOT_RUN: { label: "لم يُشغَّل", tone: "neutral" },
}

function PreviewSection({ orgId, twinId }: { orgId: string; twinId: string }) {
  const p = useApi<Preview>(`/orgs/${orgId}/twins/${twinId}/preview`)
  if (p.loading) return <Loading />
  if (p.error) return <p className="text-sm text-muted-foreground">{messageFor(p.error)}</p>
  return (
    <div className="space-y-6">
      {p.data?.tables.map((t) => (
        <div key={t.table} className="grid gap-4 lg:grid-cols-2">
          <div>
            <p className="mb-2 text-sm font-semibold text-muted-foreground">الأصل · <bdi>{t.table}</bdi></p>
            <DataTable columns={t.columns} rows={t.rows.map((r) => t.columns.map((c) => r[c][0]))} maxHeight="20rem" />
          </div>
          <div>
            <p className="mb-2 text-sm font-semibold text-twin">النظير</p>
            <DataTable columns={t.columns} rows={t.rows.map((r) => t.columns.map((c) => r[c][1]))}
              highlight={(i, j) => t.rows[i][t.columns[j]][2]} maxHeight="20rem" />
          </div>
        </div>
      ))}
    </div>
  )
}

function counts(map: Record<string, number>, labels: Record<string, string>) {
  const items = Object.entries(map).filter(([, n]) => n > 0)
  return items.length ? items.map(([k, n]) => `${labels[k] ?? "أخرى"} ${n.toLocaleString("en")}`).join(" · ") : null
}

export default function TwinPage() {
  const { twinId } = useParams<{ twinId: string }>()
  const { orgId, membership } = useCurrentMembership()
  const router = useRouter()
  const twin = useApi<Twin>(`/orgs/${orgId}/twins/${twinId}`)
  const [shareOpen, setShareOpen] = useState(false)
  const [busy, setBusy] = useState(false)
  const [showPreview, setShowPreview] = useState(false)
  const t = twin.data
  if (twin.loading) return <Loading />
  if (twin.error || !t) return <LoadError error={twin.error} />
  const isAdmin = membership?.role === "admin"
  const p = t.proof
  const pass = t.verdict === "PASS"
  const rv = t.review?.totals ?? { auto: 0, admin: 0, pending: 0 }
  const pending = rv.pending
  const shareable = pass && !t.withheld && !t.purged && pending === 0
  const safetyPass = p.leak.status === "PASS" && p.residual?.status !== "FAIL"
  const validityOk = p.validity?.status !== "FAIL"
  const linksOk = (p.links?.orphans ?? 0) === 0
  const residualCols = Object.entries(
    (t.residual?.locations ?? []).reduce<Record<string, number>>((acc, l) => {
      const k = `${l.table}.${l.column}`
      acc[k] = (acc[k] ?? 0) + 1
      return acc
    }, {}),
  )

  async function run(fn: () => Promise<unknown>, message: string) {
    setBusy(true)
    try {
      await fn()
      toast.success(message)
      router.push(`/app/o/${orgId}/datasets/${t!.dataset_id}`)
    } catch (e) {
      toast.error(messageFor(e))
      setBusy(false)
    }
  }
  const applyDecisions = () => run(() => api(`/orgs/${orgId}/twins/${t.id}/apply-decisions`, { method: "POST" }), "تُطبَّق القرارات على النظير.")
  const acceptAndApply = () => run(async () => {
    await api(`/orgs/${orgId}/datasets/${t.dataset_id}/decisions/accept`, { method: "POST" })
    await api(`/orgs/${orgId}/twins/${t.id}/apply-decisions`, { method: "POST" })
  }, "طُبّقت اقتراحات نَظير.")
  const clearColumns = () => run(() => api(`/orgs/${orgId}/datasets/${t.dataset_id}/generate`, {
    method: "POST", body: { mode: "masked", overrides: t.options?.overrides ?? {}, replace_twin_id: t.id,
      cleared_columns: [...(t.options?.cleared_columns ?? []), ...residualCols.map(([c]) => c)] },
  }), "يُعاد التوليد.")

  const sentence = !pass ? `راسب: ${t.failed_checks.map(checkName).filter((v, i, a) => a.indexOf(v) === i).join("، ")}`
    : pending ? "ناجح · قرارات بانتظارك قبل المشاركة" : "ناجح · يمكن مشاركته"

  return (
    <>
      <Link href={`/app/o/${orgId}/datasets/${t.dataset_id}`} className="mb-4 inline-flex items-center gap-1 text-sm font-semibold text-primary hover:underline">
        <ArrowRight className="size-4" /> {t.dataset_name}
      </Link>
      <PageHeader
        title={t.mode === "masked" ? "النظير المقنّع" : "النظير الاصطناعي"}
        description={<>وُلّد {formatDateTime(t.created_at)}</>}
        actions={
          <>
            <a href={`/api/orgs/${orgId}/twins/${t.id}/report.pdf`} className={buttonVariants({ variant: "ghost" })}>
              <Download data-icon="inline-start" /> التقرير
            </a>
            {!t.withheld && !t.purged ? (
              <Link href={`/app/o/${orgId}/twins/${t.id}/view`} className={buttonVariants({ variant: "outline" })}>
                <Table2 data-icon="inline-start" /> عرض النظير
              </Link>
            ) : null}
            <Button onClick={() => setShareOpen(true)} disabled={!shareable}>
              <Share2 data-icon="inline-start" /> مشاركة
            </Button>
          </>
        }
      />

      <div className={cn("mb-6 flex flex-wrap items-center gap-4 rounded-xl border px-6 py-4",
        !pass ? "border-sensitive/30 bg-sensitive-soft" : pending ? "border-primary/20 bg-accent/60" : "border-twin/30 bg-twin-soft")}>
        {pass ? <CheckCircle2 className="size-6 text-twin" aria-hidden="true" /> : <XCircle className="size-6 text-sensitive" aria-hidden="true" />}
        <p className="min-w-0 flex-1 text-lg font-bold">{sentence}</p>
        {pass && pending ? (
          <Button onClick={acceptAndApply} disabled={busy || !t.session_open}>
            {busy ? <Spinner className="size-4" /> : <Sparkles data-icon="inline-start" />} طبّق اقتراحات نَظير
          </Button>
        ) : <VerdictChip verdict={t.verdict} />}
      </div>

      {t.mode === "masked" ? (
        <p className="mb-8 flex flex-wrap items-center gap-x-3 gap-y-2 text-sm text-muted-foreground">
          <span><Num>{rv.auto}</Num> قرارات اتخذها نَظير تلقائياً، <Num>{rv.admin}</Num> بقرارك{pending ? <>، <Num>{pending}</Num> بانتظارك</> : null}</span>
          {t.decisions_stale && t.session_open ? (
            <Button size="sm" variant="outline" onClick={applyDecisions} disabled={busy}>طبّق القرارات على النظير</Button>
          ) : null}
          {pending || t.decisions_stale ? (
            <Link href={`/app/o/${orgId}/datasets/${t.dataset_id}`} className="font-semibold text-primary">راجع القرارات</Link>
          ) : null}
        </p>
      ) : null}

      {t.mode === "masked" ? (
        <div className="grid gap-6 xl:grid-cols-2">
          <section aria-labelledby="g-safety" className="space-y-3">
            <div className="flex items-center justify-between gap-3">
              <h2 id="g-safety" className="text-lg font-bold">الأمان</h2>
              <VerdictChip verdict={safetyPass ? "PASS" : "FAIL"} />
            </div>
            <div className="grid gap-4 sm:grid-cols-2">
              <VerdictCard title="التسريب" verdict={p.leak.status === "PASS" ? "PASS" : "FAIL"} value={<Num>{p.leak.leaks}</Num>}
                explanation={`معرّف حقيقي في ${p.leak.cells.toLocaleString("en")} خلية`} />
              <VerdictCard title="فحص البقايا" verdict={p.residual?.status === "FAIL" ? "FAIL" : "PASS"} value={<Num>{p.residual?.found ?? 0}</Num>}
                explanation="معرّف صالح لم يولّده نَظير" />
            </div>
          </section>
          <section aria-labelledby="g-quality" className="space-y-3">
            <div className="flex items-center justify-between gap-3">
              <h2 id="g-quality" className="flex items-center gap-2 text-lg font-bold">
                الجودة <InfoTip>تؤثر على فائدة النظير للأنظمة والتحليل، لا على الخصوصية.</InfoTip>
              </h2>
              <VerdictChip verdict={validityOk && linksOk ? "PASS" : "WARN"} />
            </div>
            <div className="grid gap-4 sm:grid-cols-2">
              <VerdictCard title="صلاحية البدائل" verdict={validityOk ? "PASS" : "WARN"}
                value={p.validity?.share != null ? <Num>{Math.round(p.validity.share * 100)}%</Num> : "—"}
                explanation={validityOk ? "تجتاز التحقق الرسمي" : "بعض البدائل لا تجتاز التحقق؛ لا تسريب"} />
              <VerdictCard title="سلامة الروابط" verdict={linksOk ? "PASS" : "WARN"} value={<Num>{p.links?.orphans ?? 0}</Num>}
                explanation={linksOk ? "روابط مكسورة بين الجداول" : "بعض الروابط انكسرت؛ لا تسريب"} />
            </div>
          </section>
        </div>
      ) : (
        <div className="grid gap-4 md:grid-cols-3">
          <VerdictCard title="التسريب" verdict={p.leak.status === "PASS" ? "PASS" : "FAIL"} value={<Num>{p.leak.leaks}</Num>}
            explanation="المعرّفات مولّدة من جديد" />
          <VerdictCard title="البُعد عن الأصل" verdict={t.privacy?.dcr?.passed ? "PASS" : "FAIL"}
            value={<Num>{`${Math.round((t.privacy?.dcr?.share_twin_closer_to_train_than_holdout ?? 0) * 100)}%`}</Num>}
            explanation="أقرب للتدريب منها لبيانات جديدة (المثالي ٥٠٪)" />
          <VerdictCard title="الفائدة" verdict={t.utility?.max_auc_drop != null ? (t.utility.max_auc_drop <= 0.05 ? "PASS" : "FAIL") : "PASS"}
            value={t.utility?.max_auc_drop != null ? <Num>{t.utility.max_auc_drop.toFixed(4)}</Num> : "—"}
            explanation={t.utility?.max_auc_drop != null ? "أكبر انخفاض في دقة النموذج" : "لم تُقس"} />
        </div>
      )}

      {t.mode === "masked" && t.residual && t.residual.found > 0 ? (
        <div className="mt-6 space-y-2 rounded-xl border border-sensitive/30 bg-sensitive-soft px-6 py-4 text-sensitive">
          <p className="font-bold">معرّفات صالحة لم يولّدها نَظير: {residualCols.map(([c, n]) => `${c} (${n})`).join("، ")}</p>
          <Button variant="outline" size="sm" disabled={busy || !t.session_open} onClick={clearColumns}>ليست معرّفات، أعد التوليد</Button>
        </div>
      ) : null}

      {t.summary ? (
        <dl className="mt-8 grid gap-3 rounded-xl border border-border bg-card px-6 py-4 text-sm shadow-card md:grid-cols-3">
          <div><dt className="font-bold">استُبدل</dt><dd className="text-muted-foreground">{counts(t.summary.replaced, KIND_AR) ?? "لا شيء"}</dd></div>
          <div><dt className="font-bold">نُظِّف</dt><dd className="text-muted-foreground">
            {counts(t.summary.cleaned, RULE_LABEL) ?? (t.summary.cleaning_decision === "skipped" ? "تخطّيتَ التنظيف" : "لا حاجة")}
          </dd></div>
          <div><dt className="flex items-center gap-1 font-bold">رمز التحقق <InfoTip>كل صف مشارَك يحمل رمزاً مشفّراً يثبت مصدره ويربطه بسجله الحقيقي عند إعادته، دون أي جدول ربط.</InfoTip></dt>
            <dd className="text-muted-foreground">{t.token ? <><KeyRound className="me-1 inline size-3.5" aria-hidden="true" />على كل صف مشارَك</> : "—"}</dd></div>
        </dl>
      ) : null}

      <details className="mt-8 rounded-xl border border-border bg-card px-5 py-3 shadow-card">
        <summary className="cursor-pointer font-semibold text-muted-foreground">تفاصيل للمختصين</summary>
        <div className="mt-5 space-y-8">
          {t.mode === "masked" && isAdmin && t.session_open && !t.withheld ? (
            showPreview ? <PreviewSection orgId={orgId} twinId={t.id} /> : (
              <Button variant="outline" onClick={() => setShowPreview(true)}>
                <ShieldAlert data-icon="inline-start" /> عرض المعاينة (تتضمّن قيماً أصلية)
              </Button>
            )
          ) : null}
          <div className="overflow-x-auto rounded-lg border border-border">
            <Table>
              <TableHeader className="bg-muted/60">
                <TableRow>
                  <TableHead className="px-4 text-start font-bold">الفحص</TableHead>
                  <TableHead className="px-4 text-start font-bold">النتيجة</TableHead>
                  <TableHead className="px-4 text-start font-bold">يحسم</TableHead>
                  <TableHead className="px-4 text-start font-bold">التفاصيل</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {t.checks.map((c) => (
                  <TableRow key={c.name}>
                    <TableCell className="px-4 py-2.5 font-semibold">{checkName(c.name)}</TableCell>
                    <TableCell className="px-4 py-2.5">
                      {c.status === "FAIL" && !c.blocking ? <Chip tone="review">تنبيه</Chip>
                        : <Chip tone={STATUS[c.status]?.tone ?? "neutral"}>{STATUS[c.status]?.label ?? "—"}</Chip>}
                    </TableCell>
                    <TableCell className="px-4 py-2.5">{c.blocking ? "نعم" : "—"}</TableCell>
                    <TableCell className="max-w-xl px-4 py-2.5 text-sm whitespace-normal text-muted-foreground">{checkDetail(c)}</TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </div>
          <ul className="list-disc space-y-1.5 ps-6 text-sm leading-7 text-muted-foreground">
            {t.limitations_ar.map((l) => <li key={l}>{l}</li>)}
          </ul>
          <a href={`/api/orgs/${orgId}/twins/${t.id}/report.json`} className="inline-block text-sm text-primary hover:underline">
            تنزيل البيانات التقنية (JSON)
          </a>
        </div>
      </details>

      <ShareDialog orgId={orgId} twinId={t.id} open={shareOpen} onOpenChange={setShareOpen} />
    </>
  )
}
