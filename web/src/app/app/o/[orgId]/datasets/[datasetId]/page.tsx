"use client"

import Link from "next/link"
import { useParams, useRouter } from "next/navigation"
import { useEffect, useMemo, useState } from "react"
import { ChevronLeft, ChevronRight, FileCheck2, Link2, ScanSearch, Table2, Trash2, Wand2 } from "lucide-react"
import { toast } from "sonner"

import { CleaningPanel } from "@/components/cleaning"
import { AnswerKeyCheck, FoundByType, ReviewQueue } from "@/components/detection-extras"
import { reasonAr } from "@/lib/labels"
import { HighlightedText, MarkLegend, useNow } from "@/components/data"
import { DTYPE_LABEL, DatasetStatus, KIND_LABEL, STAGE_LABEL, TAG_LABEL } from "@/components/dataset"
import { NativeSelect } from "@/components/form"
import { LoadError, Loading, useCurrentMembership } from "@/components/org"
import { Chip, InlineError, Ltr, Notice, Num, PageHeader, Section, Spinner, StatCard, VerdictChip } from "@/components/nz"
import { Button } from "@/components/ui/button"
import { Progress } from "@/components/ui/progress"
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table"
import { ApiError, api, messageFor } from "@/lib/api"
import type { ColumnInfo, Dataset, Note } from "@/lib/types"
import { formatDateTime, useApi } from "@/lib/use-api"
import { cn } from "@/lib/utils"

type Choice = "auto" | "keep" | "drop" | `pseudo:${string}`

function overrideFor(col: ColumnInfo, choice: Choice) {
  if (choice === "keep") return { tag: "NORMAL", kind: null, action: { action: "keep" } }
  if (choice === "drop") return { tag: col.tag, kind: col.kind, action: { action: "drop" } }
  if (choice.startsWith("pseudo:")) return { tag: "DIRECT_ID", kind: choice.slice(7) }
  return null
}

function JobBar({ label, progress }: { label: string; progress: number }) {
  return (
    <div className="rounded-xl border border-border bg-card p-5 shadow-card">
      <div className="mb-3 flex items-center gap-3 font-bold">
        <Spinner className="size-4 text-primary" /> {label}
      </div>
      <Progress value={Math.max(8, progress)} />
    </div>
  )
}

function NoteViewer({ orgId, ds }: { orgId: string; ds: Dataset }) {
  const count = ds.summary?.notes.length ?? 0
  const [i, setI] = useState(0)
  const [view, setView] = useState<"nazeer" | "baseline">("nazeer")
  const [note, setNote] = useState<Note | null>(null)
  const [err, setErr] = useState<string | null>(null)
  const spans = ds.summary!.spans

  useEffect(() => {
    if (!count || !ds.session_open) return
    let alive = true
    api<Note>(`/orgs/${orgId}/datasets/${ds.id}/notes/${i}`)
      .then((n) => alive && (setNote(n), setErr(null)))
      .catch((e) => alive && setErr(messageFor(e)))
    return () => {
      alive = false
    }
  }, [orgId, ds.id, ds.session_open, i, count])

  return (
    <Section title="البيانات الشخصية داخل النصوص" description="نفس الملاحظة كما يراها نَظير، وكما تراها أداة تقليدية تبحث بأنماط بسيطة.">
      <div className="grid gap-4 sm:grid-cols-2">
        <button
          type="button"
          onClick={() => setView("nazeer")}
          className={cn("rounded-xl border bg-card p-5 text-start shadow-card", view === "nazeer" ? "border-twin ring-2 ring-twin/25" : "border-border")}
        >
          <p className="text-sm font-bold text-muted-foreground">نَظير</p>
          <p className="mt-2 text-[2rem] leading-none font-bold"><Num>{spans.nazeer_found.toLocaleString("en")}</Num></p>
          <p className="mt-2 text-sm text-muted-foreground">معرّفاً وُجد في النصوص · كل رقم اجتاز التحقق الرسمي</p>
        </button>
        <button
          type="button"
          onClick={() => setView("baseline")}
          className={cn("rounded-xl border bg-card p-5 text-start shadow-card", view === "baseline" ? "border-primary ring-2 ring-primary/20" : "border-border")}
        >
          <p className="text-sm font-bold text-muted-foreground">أداة تقليدية</p>
          <p className="mt-2 text-[2rem] leading-none font-bold"><Num>{spans.baseline_found.toLocaleString("en")}</Num></p>
          <p className="mt-2 text-sm text-muted-foreground">
            علامة، منها <Num>{spans.baseline_false_alarms.toLocaleString("en")}</Num> إنذار كاذب لا يجتاز التحقق
          </p>
        </button>
      </div>
      {!count ? (
        <Notice>لا توجد نصوص حرة فيها معرّفات في هذه البيانات.</Notice>
      ) : !ds.session_open ? (
        <Notice>حُذفت الأصول، فلا يمكن عرض النصوص الأصلية. الأرقام أعلاه محفوظة بلا أي قيمة.</Notice>
      ) : (
        <div className="rounded-xl border border-border bg-card shadow-card">
          <div className="flex flex-wrap items-center justify-between gap-3 border-b border-border px-5 py-3">
            <div className="flex items-center gap-1 rounded-lg bg-muted p-1" role="tablist" aria-label="طريقة العرض">
              {(["nazeer", "baseline"] as const).map((v) => (
                <button
                  key={v}
                  role="tab"
                  aria-selected={view === v}
                  onClick={() => setView(v)}
                  className={cn("h-8 rounded-md px-3 text-sm font-semibold", view === v ? "bg-card shadow-card" : "text-muted-foreground")}
                >
                  {v === "nazeer" ? "نَظير" : "أداة تقليدية"}
                </button>
              ))}
            </div>
            <div className="flex items-center gap-2 text-sm text-muted-foreground">
              {note ? (
                <span>
                  <Ltr>{note.table}.{note.column}</Ltr> · ملاحظة <Num>{i + 1}</Num> من <Num>{count}</Num>
                </span>
              ) : null}
              <Button variant="outline" size="icon-sm" aria-label="السابقة" disabled={i === 0} onClick={() => setI(i - 1)}>
                <ChevronRight />
              </Button>
              <Button variant="outline" size="icon-sm" aria-label="التالية" disabled={i >= count - 1} onClick={() => setI(i + 1)}>
                <ChevronLeft />
              </Button>
            </div>
          </div>
          <div className="px-5 py-4">
            {err ? <InlineError>{err}</InlineError> : note ? (
              <HighlightedText text={note.text} marks={view === "nazeer" ? note.nazeer : note.baseline} />
            ) : <Spinner className="size-4" />}
          </div>
          <div className="border-t border-border px-5 py-3"><MarkLegend /></div>
        </div>
      )}
    </Section>
  )
}

export default function DatasetPage() {
  const { datasetId } = useParams<{ datasetId: string }>()
  const { orgId, membership } = useCurrentMembership()
  const router = useRouter()
  const ds = useApi<Dataset>(`/orgs/${orgId}/datasets/${datasetId}`)
  const now = useNow(5000)
  const [choices, setChoices] = useState<Record<string, Choice>>({})
  const [mode, setMode] = useState<"masked" | "synthetic">("masked")
  const [target, setTarget] = useState("")
  const [approveReview, setApproveReview] = useState(false)
  const [busy, setBusy] = useState(false)
  const d = ds.data

  const generating = d?.generate_job && ["queued", "running"].includes(d.generate_job.status)
  const processing = d?.status === "processing"
  useEffect(() => {
    if (!processing && !generating) return
    const t = setInterval(() => void ds.reload(), 2000)
    return () => clearInterval(t)
  }, [processing, generating, ds])

  // When a generation in progress (started here or from the twin page) finishes, open its twin.
  const [watching, setWatching] = useState<string | null>(null)
  useEffect(() => {
    const j = d?.generate_job
    if (!watching && j && ["queued", "running"].includes(j.status)) {
      // eslint-disable-next-line react-hooks/set-state-in-effect
      setWatching(j.id)
    }
  }, [d?.generate_job, watching])
  useEffect(() => {
    const j = d?.generate_job
    if (!watching || !j || j.id !== watching) return
    if (j.status === "succeeded" && j.result?.twin_id) router.push(`/app/o/${orgId}/twins/${j.result.twin_id}`)
    if (j.status === "failed") {
      toast.error(messageFor(new ApiError(0, j.error_code ?? "error")))
      // eslint-disable-next-line react-hooks/set-state-in-effect
      setWatching(null)
    }
  }, [d?.generate_job, watching, router, orgId])

  const overrides = useMemo(() => {
    const out: Record<string, unknown> = {}
    for (const t of d?.summary?.tables ?? [])
      for (const c of t.columns) {
        const o = overrideFor(c, choices[`${t.name}.${c.name}`] ?? "auto")
        if (o) out[`${t.name}.${c.name}`] = o
      }
    return out
  }, [choices, d?.summary])

  if (ds.loading && !d) return <Loading />
  if (ds.error || !d) return <LoadError error={ds.error} />

  const s = d.summary
  const syntheticAllowed = (s?.total_rows ?? 0) <= 15000
  const sensitive = s?.tables.flatMap((t) => t.columns).filter((c) => c.tag === "DIRECT_ID").length ?? 0

  async function generate() {
    setBusy(true)
    try {
      const r = await api<{ job_id: string }>(`/orgs/${orgId}/datasets/${datasetId}/generate`, {
        method: "POST",
        body: { mode, overrides, approve_review: approveReview, target: mode === "synthetic" && target ? target : null },
      })
      setWatching(r.job_id)
      await ds.reload()
    } catch (e) {
      toast.error(messageFor(e))
    } finally {
      setBusy(false)
    }
  }

  async function endSession() {
    try {
      await api(`/orgs/${orgId}/datasets/${datasetId}/end-session`, { method: "POST" })
      toast.success("حُذفت البيانات الأصلية.")
      await ds.reload()
    } catch (e) {
      toast.error(messageFor(e))
    }
  }

  return (
    <>
      <PageHeader
        title={d.name}
        description={<>رُفعت {formatDateTime(d.created_at)}</>}
        actions={<DatasetStatus ds={d} now={now} />}
      />

      {d.session_open && d.status !== "failed" ? (
        <div className="mb-8 flex flex-wrap items-center justify-between gap-3 rounded-xl border border-review/30 bg-review-soft px-5 py-3.5 text-sm text-review">
          <span>
            الأصول محفوظة مشفّرة لجلسة المعالجة فقط، وتُحذف تلقائياً خلال <strong><Num>{Math.max(0, Math.ceil((new Date(d.session_expires_at + "Z").getTime() - now) / 60000))}</Num> دقيقة</strong>.
          </span>
          <Button size="sm" variant="outline" onClick={endSession}>
            <Trash2 data-icon="inline-start" />
            احذف الأصول الآن
          </Button>
        </div>
      ) : null}

      {processing ? (
        <JobBar label={STAGE_LABEL[d.process_job?.stage ?? "reading_files"] ?? "جارٍ المعالجة"} progress={d.process_job?.progress ?? 10} />
      ) : d.status === "failed" ? (
        <InlineError>{messageFor(new ApiError(0, d.error_code ?? "error"))}</InlineError>
      ) : s ? (
        <div className="space-y-10">
          <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
            <StatCard label="الجداول" value={<Num>{s.tables.length}</Num>} icon={Table2} />
            <StatCard label="الصفوف" value={<Num>{s.total_rows.toLocaleString("en")}</Num>} icon={Table2} />
            <StatCard label="أعمدة معرّفات" value={<Num>{sensitive}</Num>} icon={ScanSearch} />
            <StatCard label="الروابط بين الجداول" value={<Num>{s.relationships.length}</Num>} icon={Link2}
              hint={s.relationships.length ? undefined : "تُعامل الجداول باستقلال"} />
          </div>

          <FoundByType ds={d} />

          <CleaningPanel orgId={orgId} ds={d} onApplied={() => void ds.reload()} />

          <Section title="مراجعة الكشف" description="ما اكتشفه نَظير في كل عمود، ولماذا. غيّر الإجراء إن لزم؛ كل تعديل يُسجَّل في التقرير.">
            {s.tables.map((t) => (
              <div key={t.name} className="overflow-x-auto rounded-xl border border-border bg-card shadow-card">
                <div className="flex flex-wrap items-center justify-between gap-2 border-b border-border px-5 py-3">
                  <p className="font-bold"><Ltr>{t.name}</Ltr></p>
                  <p className="text-sm text-muted-foreground"><Num>{t.rows.toLocaleString("en")}</Num> صف</p>
                </div>
                <Table>
                  <TableHeader className="bg-muted/60">
                    <TableRow>
                      <TableHead className="px-5 text-start font-bold">العمود</TableHead>
                      <TableHead className="px-5 text-start font-bold">النوع</TableHead>
                      <TableHead className="px-5 text-start font-bold">التصنيف</TableHead>
                      <TableHead className="px-5 text-start font-bold">الثقة</TableHead>
                      <TableHead className="px-5 text-start font-bold">الدليل</TableHead>
                      <TableHead className="px-5 text-start font-bold">الإجراء</TableHead>
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {t.columns.map((c) => {
                      const key = `${t.name}.${c.name}`
                      const tag = TAG_LABEL[c.tag]
                      return (
                        <TableRow key={key}>
                          <TableCell className="px-5 py-3 font-semibold"><bdi>{c.name}</bdi></TableCell>
                          <TableCell className="px-5 py-3 text-muted-foreground">{DTYPE_LABEL[c.dtype] ?? c.dtype}</TableCell>
                          <TableCell className="px-5 py-3">
                            <span className="flex flex-wrap gap-1.5">
                              <Chip tone={tag.tone}>{tag.label}</Chip>
                              {c.kind ? <Chip tone="sensitive">{KIND_LABEL[c.kind] ?? c.kind}</Chip> : null}
                              {c.needs_review ? <Chip tone="review">للمراجعة</Chip> : null}
                            </span>
                          </TableCell>
                          <TableCell className="px-5 py-3"><Num>{Math.round(c.confidence * 100)}%</Num></TableCell>
                          <TableCell className="max-w-72 px-5 py-3 text-sm whitespace-normal text-muted-foreground">{reasonAr(c.reason)}</TableCell>
                          <TableCell className="px-5 py-3">
                            <NativeSelect
                              aria-label={`إجراء العمود ${c.name}`}
                              className="h-9 min-w-44 text-sm"
                              value={choices[key] ?? "auto"}
                              onChange={(e) => setChoices({ ...choices, [key]: e.target.value as Choice })}
                            >
                              <option value="auto">حسب السياسة (تلقائي)</option>
                              <option value="keep">إبقاء كما هو</option>
                              <option value="drop">حذف العمود من النظير</option>
                              {Object.entries(KIND_LABEL).map(([k, l]) => (
                                <option key={k} value={`pseudo:${k}`}>استبدال ببديل: {l}</option>
                              ))}
                            </NativeSelect>
                          </TableCell>
                        </TableRow>
                      )
                    })}
                  </TableBody>
                </Table>
              </div>
            ))}
            {s.relationships.length ? (
              <p className="text-sm text-muted-foreground">
                الروابط المكتشفة:{" "}
                {s.relationships.map((r, i) => (
                  <span key={i} className="me-3"><Ltr>{r.child_table}.{r.child_column} → {r.parent_table}.{r.parent_column}</Ltr></span>
                ))}
              </p>
            ) : null}
            {s.ingest.some((n) => n.header === "generated" || n.dropped_empty_columns || n.encoding === "windows-1256" || (n as { skipped_title_rows?: number }).skipped_title_rows) ? (
              <Notice>
                {s.ingest.map((n) => (
                  <span key={n.table} className="block">
                    <Ltr>{n.source}</Ltr>:{" "}
                    {n.encoding === "windows-1256" ? "ترميز ويندوز العربي (1256) · " : null}
                    {(n as { skipped_title_rows?: number }).skipped_title_rows ? <>تُجوهل <Num>{(n as { skipped_title_rows?: number }).skipped_title_rows}</Num> سطر عنوان فوق الجدول · </> : null}
                    {n.header === "generated" ? "بلا صف عناوين (سُمّيت الأعمدة col_1…) · " : null}
                    {n.dropped_empty_columns ? <>حُذف <Num>{n.dropped_empty_columns}</Num> عمود فارغ · </> : null}
                    {n.dropped_empty_rows ? <>حُذف <Num>{n.dropped_empty_rows}</Num> صف فارغ</> : null}
                  </span>
                ))}
              </Notice>
            ) : null}
          </Section>

          <NoteViewer orgId={orgId} ds={d} />

          <ReviewQueue orgId={orgId} ds={d} />

          <AnswerKeyCheck orgId={orgId} ds={d} />

          <Section title="توليد النظير">
            {generating ? (
              <JobBar label={STAGE_LABEL.generating} progress={d.generate_job?.progress ?? 20} />
            ) : !d.session_open ? (
              <Notice>انتهت جلسة المعالجة وحُذفت الأصول. ارفع الملفات مجدداً لتوليد نظير جديد.</Notice>
            ) : (
              <div className="space-y-5 rounded-xl border border-border bg-card p-6 shadow-card">
                <fieldset className="grid gap-3 sm:grid-cols-2">
                  <legend className="sr-only">نوع النظير</legend>
                  {(
                    [
                      ["masked", "نظير مقنّع (موصى به)", "نفس الصفوف، وكل شخص يُستبدل ببديل صالح ومتّسق. يصلح للاختبار والتطوير."],
                      ["synthetic", "نظير اصطناعي · تجريبي", "صفوف جديدة بنفس الأنماط للتحليل؛ هامش الخصوصية فيه أضيق ويتذبذب بين التقسيمات."],
                    ] as const
                  ).map(([v, title, text]) => {
                    const disabled = v === "synthetic" && !syntheticAllowed
                    return (
                      <label
                        key={v}
                        className={cn(
                          "flex cursor-pointer flex-col gap-1.5 rounded-xl border p-4",
                          mode === v ? "border-primary bg-accent ring-2 ring-primary/20" : "border-border",
                          disabled && "cursor-not-allowed opacity-60",
                        )}
                      >
                        <input type="radio" name="mode" value={v} checked={mode === v} disabled={disabled}
                          onChange={() => setMode(v)} className="sr-only" />
                        <span className="font-bold">{title}</span>
                        <span className="text-sm leading-6 text-muted-foreground">{text}</span>
                        {disabled ? <span className="text-sm text-review">متاح حتى <Num>15,000</Num> صف في النسخة المستضافة.</span> : null}
                      </label>
                    )
                  })}
                </fieldset>
                {mode === "synthetic" ? (
                  <div className="max-w-md space-y-2">
                    <label className="text-sm font-semibold" htmlFor="target">عمود لاختبار الفائدة (اختياري)</label>
                    <NativeSelect id="target" value={target} onChange={(e) => setTarget(e.target.value)}>
                      <option value="">بلا اختبار فائدة</option>
                      {s.tables.flatMap((t) => t.columns.filter((c) => c.dtype === "numeric" && c.tag !== "DIRECT_ID")
                        .map((c) => <option key={`${t.name}.${c.name}`} value={`high_${c.name}=${c.name}>p90`}>أعلى 10% في {c.name}</option>))}
                      {s.tables.flatMap((t) => t.columns.filter((c) => c.dtype === "categorical" && c.unique === 2)
                        .map((c) => <option key={`b${t.name}.${c.name}`} value={c.name}>{c.name}</option>))}
                    </NativeSelect>
                    <p className="text-xs text-muted-foreground">بدونه يعمل التقرير كاملاً، ويُذكر أن الفائدة لم تُقس.</p>
                  </div>
                ) : null}
                {mode === "masked" && s.review?.total ? (
                  <label className="flex items-start gap-3 text-sm">
                    <input type="checkbox" className="mt-1 size-4 accent-[var(--color-primary)]" checked={approveReview}
                      onChange={(e) => setApproveReview(e.target.checked)} />
                    <span>استبدل أيضاً القيم المعلّقة للمراجعة (<Num>{s.review.total}</Num>). بدون ذلك تُترك كما هي.</span>
                  </label>
                ) : null}
                {Object.keys(overrides).length ? (
                  <p className="text-sm text-muted-foreground">سيُطبَّق <Num>{Object.keys(overrides).length}</Num> تعديل يدوي ويُسجَّل في التقرير.</p>
                ) : null}
                <Button size="lg" onClick={generate} disabled={busy || membership === undefined}>
                  {busy ? <Spinner className="size-4" /> : <Wand2 data-icon="inline-start" />}
                  ولّد النظير
                </Button>
              </div>
            )}
          </Section>

          {d.twins.length ? (
            <Section title="النظائر المولّدة">
              <ul className="divide-y divide-border rounded-xl border border-border bg-card shadow-card">
                {d.twins.map((t) => (
                  <li key={t.id}>
                    <Link href={`/app/o/${orgId}/twins/${t.id}`} className="flex flex-wrap items-center justify-between gap-3 px-5 py-4 hover:bg-muted/50">
                      <span className="flex items-center gap-3 font-semibold">
                        <FileCheck2 className="size-4 text-muted-foreground" aria-hidden="true" />
                        {t.mode === "masked" ? "نظير مقنّع" : "نظير اصطناعي"}
                        <span className="text-sm font-normal text-muted-foreground">{formatDateTime(t.created_at)}</span>
                      </span>
                      <VerdictChip verdict={t.verdict} />
                    </Link>
                  </li>
                ))}
              </ul>
            </Section>
          ) : null}
        </div>
      ) : null}
    </>
  )
}
