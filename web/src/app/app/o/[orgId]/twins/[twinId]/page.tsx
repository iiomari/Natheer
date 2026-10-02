"use client"

import Link from "next/link"
import { useParams, useRouter } from "next/navigation"
import { useState } from "react"
import { ArrowRight, CheckCircle2, Download, Share2, ShieldAlert, Wand2, XCircle } from "lucide-react"
import { toast } from "sonner"

import { DataTable } from "@/components/data"
import { ShareDialog } from "@/components/share-dialog"
import { LoadError, Loading, useCurrentMembership } from "@/components/org"
import { Chip, Ltr, Notice, Num, PageHeader, Section, Spinner, VerdictCard, VerdictChip } from "@/components/nz"
import { Button, buttonVariants } from "@/components/ui/button"
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table"
import { api, messageFor } from "@/lib/api"
import type { Twin } from "@/lib/types"
import { formatDateTime, useApi } from "@/lib/use-api"
import { cn } from "@/lib/utils"

type Preview = { tables: { table: string; columns: string[]; rows: Record<string, [string, string, boolean]>[] }[] }

const CHECK_LABEL: Record<string, string> = {
  leak_scan: "فحص التسريب",
  exact_copies: "نسخ مطابقة للأصل",
  human_review: "المراجعة البشرية",
  free_text_replacement: "الاستبدال داخل النصوص",
  holdout_split: "فصل بيانات الاختبار قبل التدريب",
  dcr: "البُعد عن بيانات التدريب",
  utility_tstr: "الفائدة للتحليل",
  fidelity: "التشابه الإحصائي",
  synthesizer: "النموذج المولِّد",
  dcr_per_stratum: "البُعد لكل فئة",
}
const STATUS: Record<string, { label: string; tone: "twin" | "sensitive" | "neutral" }> = {
  PASS: { label: "ناجح", tone: "twin" },
  FAIL: { label: "راسب", tone: "sensitive" },
  INFO: { label: "معلومة", tone: "neutral" },
  NOT_RUN: { label: "لم يُشغَّل", tone: "neutral" },
}

function checkName(name: string) {
  if (name.startsWith("k_anonymity_before_fix")) return "خطر التعرّف قبل الإصلاح"
  if (name.startsWith("k_anonymity")) return "خطر التعرّف بالتركيب"
  return CHECK_LABEL[name] ?? name
}

function PreviewSection({ orgId, twinId }: { orgId: string; twinId: string }) {
  const p = useApi<Preview>(`/orgs/${orgId}/twins/${twinId}/preview`)
  if (p.loading) return <Loading />
  if (p.error) return <Notice>{messageFor(p.error)}</Notice>
  return (
    <div className="space-y-6">
      {p.data?.tables.map((t) => (
        <div key={t.table} className="space-y-2">
          <p className="font-bold"><Ltr>{t.table}</Ltr></p>
          <div className="grid gap-4 lg:grid-cols-2">
            <div>
              <p className="mb-2 text-sm font-semibold text-muted-foreground">الأصل</p>
              <DataTable columns={t.columns} rows={t.rows.map((r) => t.columns.map((c) => r[c][0]))} maxHeight="20rem" />
            </div>
            <div>
              <p className="mb-2 text-sm font-semibold text-twin">النظير · الخلايا المتغيّرة مظلّلة</p>
              <DataTable
                columns={t.columns}
                rows={t.rows.map((r) => t.columns.map((c) => r[c][1]))}
                highlight={(i, j) => t.rows[i][t.columns[j]][2]}
                maxHeight="20rem"
              />
            </div>
          </div>
        </div>
      ))}
    </div>
  )
}

export default function TwinPage() {
  const { twinId } = useParams<{ twinId: string }>()
  const { orgId, membership } = useCurrentMembership()
  const router = useRouter()
  const twin = useApi<Twin>(`/orgs/${orgId}/twins/${twinId}`)
  const [shareOpen, setShareOpen] = useState(false)
  const [fixBusy, setFixBusy] = useState(false)
  const [showPreview, setShowPreview] = useState(false)
  const t = twin.data
  if (twin.loading) return <Loading />
  if (twin.error || !t) return <LoadError error={twin.error} />
  const isAdmin = membership?.role === "admin"
  const p = t.proof
  const k = t.k_anonymity
  const fix = k?.suggestions?.find((s) => s.reaches_k_min)
  const shareable = t.verdict === "PASS" && !t.withheld && !t.purged

  async function applyFix() {
    if (!fix) return
    setFixBusy(true)
    try {
      await api(`/orgs/${orgId}/datasets/${t!.dataset_id}/generate`, { method: "POST", body: { mode: "masked", apply_fix: fix.name } })
      toast.success("يجري توليد النظير بالإصلاح المقترح.")
      router.push(`/app/o/${orgId}/datasets/${t!.dataset_id}`)
    } catch (e) {
      toast.error(messageFor(e))
      setFixBusy(false)
    }
  }

  const pass = t.verdict === "PASS"
  return (
    <>
      <Link href={`/app/o/${orgId}/datasets/${t.dataset_id}`} className="mb-4 inline-flex items-center gap-1 text-sm font-semibold text-primary hover:underline">
        <ArrowRight className="size-4" /> {t.dataset_name}
      </Link>
      <PageHeader
        title={t.mode === "masked" ? "تقرير النظير المقنّع" : "تقرير النظير الاصطناعي"}
        description={<>وُلّد {formatDateTime(t.created_at)}</>}
        actions={
          <>
            <a href={`/api/orgs/${orgId}/twins/${t.id}/report.json`} className={buttonVariants({ variant: "outline" })}>
              <Download data-icon="inline-start" /> تنزيل التقرير
            </a>
            <Button onClick={() => setShareOpen(true)} disabled={!shareable} title={shareable ? undefined : "المشاركة متاحة للنظير الناجح فقط"}>
              <Share2 data-icon="inline-start" /> مشاركة
            </Button>
          </>
        }
      />

      <div
        className={cn(
          "mb-8 flex flex-wrap items-center gap-4 rounded-xl border px-6 py-5",
          pass ? "border-twin/30 bg-twin-soft" : "border-sensitive/30 bg-sensitive-soft",
        )}
      >
        {pass ? <CheckCircle2 className="size-7 text-twin" aria-hidden="true" /> : <XCircle className="size-7 text-sensitive" aria-hidden="true" />}
        <div className="min-w-0 flex-1">
          <p className="text-lg font-bold">{pass ? "النتيجة: ناجح · يمكن مشاركة هذا النظير" : "النتيجة: راسب · لا يمكن مشاركة هذا النظير"}</p>
          {!pass ? (
            <p className="mt-1 text-sm">الفحص الذي لم ينجح: {t.failed_checks.map(checkName).filter((v, i, a) => a.indexOf(v) === i).join("، ")}</p>
          ) : null}
        </div>
        <VerdictChip verdict={t.verdict} />
      </div>

      {t.mode === "masked" ? (
        <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-4">
          <VerdictCard title="التسريب" verdict={p.leak.status === "PASS" ? "PASS" : "FAIL"}
            value={<Num>{p.leak.leaks}</Num>}
            explanation={`معرّف حقيقي في ${p.leak.cells.toLocaleString("en")} خلية فُحصت كلها.`} />
          <VerdictCard title="صلاحية البدائل" verdict={p.validity?.status === "PASS" || p.validity?.status === "NOT_RUN" ? "PASS" : "FAIL"}
            value={p.validity?.share != null ? <Num>{Math.round(p.validity.share * 100)}%</Num> : "—"}
            explanation={p.validity?.share != null ? "من البدائل تجتاز خوارزميات التحقق الرسمية." : "لا توجد أعمدة معرّفات منظّمة لفحصها."} />
          <VerdictCard title="سلامة الروابط" verdict={(p.links?.orphans ?? 0) === 0 ? "PASS" : "FAIL"}
            value={<Num>{p.links?.orphans ?? 0}</Num>}
            explanation="روابط مكسورة بين الجداول بعد الاستبدال." />
          {k ? (
            <VerdictCard title="خطر التعرّف بالتركيب" verdict={k.passed_after ? "PASS" : "FAIL"}
              value={k.applied_fix ? <Num>{`k = ${k.k_before} → ${k.k_after}`}</Num> : <Num>{`k = ${k.k_after}`}</Num>}
              explanation={k.passed_after
                ? `كل شخص يشبهه ${k.k_after} على الأقل في ${k.quasi_columns.join("، ")}.`
                : `يمكن تمييز بعض الأشخاص بـ ${k.quasi_columns.join("، ")} معاً (الحد الأدنى ${k.k_min}).`} />
          ) : (
            <VerdictCard title="خطر التعرّف بالتركيب" verdict="PASS" value="—" explanation="لا توجد أعمدة شبه معرِّفة تجتمع على شخص." />
          )}
        </div>
      ) : (
        <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
          <VerdictCard title="التسريب" verdict={p.leak.status === "PASS" ? "PASS" : "FAIL"} value={<Num>{p.leak.leaks}</Num>}
            explanation="المعرّفات في النظير الاصطناعي مولَّدة من جديد ولا تساوي أي أصل." />
          <VerdictCard title="البُعد عن البيانات الحقيقية" verdict={t.privacy?.dcr?.passed ? "PASS" : "FAIL"}
            value={<Num>{`${Math.round((t.privacy?.dcr?.share_twin_closer_to_train_than_holdout ?? 0) * 100)}%`}</Num>}
            explanation="من الصفوف أقرب لبيانات التدريب منها لبيانات لم يرها النموذج (المثالي 50%)." />
          <VerdictCard title="الفائدة للتحليل" verdict={t.utility?.max_auc_drop != null ? (t.utility.max_auc_drop <= 0.05 ? "PASS" : "FAIL") : "PASS"}
            value={t.utility?.max_auc_drop != null ? <Num>{t.utility.max_auc_drop.toFixed(4)}</Num> : "—"}
            explanation={t.utility?.max_auc_drop != null ? "أكبر انخفاض في دقة نموذج تنبؤ تدرّب على النظير." : "لم يُختر عمود هدف، فلم تُقس الفائدة."} />
        </div>
      )}

      {k && !k.passed_after && fix ? (
        <div className="mt-6 flex flex-wrap items-center justify-between gap-4 rounded-xl border border-review/30 bg-review-soft px-6 py-5">
          <div className="text-review">
            <p className="font-bold">إصلاح مقترح لخطر التعرّف</p>
            <p className="mt-1 text-sm">
              <Num>{`k = ${fix.k_before} → ${fix.k_after}`}</Num> · يغيّر <Num>{fix.rows_affected}</Num> صفاً · <Ltr>{fix.description}</Ltr>
            </p>
          </div>
          <Button onClick={applyFix} disabled={fixBusy || !t.session_open}>
            {fixBusy ? <Spinner className="size-4" /> : <Wand2 data-icon="inline-start" />}
            طبّق الإصلاح المقترح
          </Button>
        </div>
      ) : null}
      {k?.applied_fix ? (
        <p className="mt-4 text-sm text-muted-foreground">
          طُبّق الإصلاح «<Ltr>{k.applied_fix.name}</Ltr>»، ويبقى فشل ما قبل الإصلاح مسجّلاً في التقرير.
        </p>
      ) : null}

      {t.mode === "masked" && isAdmin && t.session_open && !t.withheld ? (
        <Section title="قبل وبعد" description="سجل واحد وصفوفه المرتبطة. للمدير فقط، وأثناء جلسة المعالجة." className="mt-10">
          {showPreview ? (
            <PreviewSection orgId={orgId} twinId={t.id} />
          ) : (
            <Button variant="outline" onClick={() => setShowPreview(true)}>
              <ShieldAlert data-icon="inline-start" /> عرض المعاينة (تتضمّن قيماً أصلية)
            </Button>
          )}
        </Section>
      ) : null}

      <Section title="كل الفحوصات" className="mt-10">
        <div className="overflow-x-auto rounded-xl border border-border bg-card shadow-card">
          <Table>
            <TableHeader className="bg-muted/60">
              <TableRow>
                <TableHead className="px-5 text-start font-bold">الفحص</TableHead>
                <TableHead className="px-5 text-start font-bold">النتيجة</TableHead>
                <TableHead className="px-5 text-start font-bold">يحسم النتيجة</TableHead>
                <TableHead className="px-5 text-start font-bold">التفاصيل</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {t.checks.map((c) => (
                <TableRow key={c.name}>
                  <TableCell className="px-5 py-3 font-semibold">{checkName(c.name)}</TableCell>
                  <TableCell className="px-5 py-3"><Chip tone={STATUS[c.status]?.tone ?? "neutral"}>{STATUS[c.status]?.label ?? c.status}</Chip></TableCell>
                  <TableCell className="px-5 py-3">{c.blocking ? "نعم" : "—"}</TableCell>
                  <TableCell className="max-w-xl px-5 py-3 text-sm whitespace-normal text-muted-foreground"><Ltr>{c.detail}</Ltr></TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </div>
      </Section>

      <Section title="حدود معروفة" className="mt-10">
        <ul className="list-disc space-y-2 ps-6 text-sm leading-7 text-muted-foreground">
          {t.limitations.map((l) => <li key={l}><Ltr>{l}</Ltr></li>)}
        </ul>
      </Section>

      <ShareDialog orgId={orgId} twinId={t.id} open={shareOpen} onOpenChange={setShareOpen} />
    </>
  )
}
