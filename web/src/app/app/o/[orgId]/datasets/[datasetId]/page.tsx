"use client"

import Link from "next/link"
import { useParams, useRouter } from "next/navigation"
import { useEffect, useMemo, useState } from "react"
import { ChevronLeft, ChevronRight, FileCheck2, Trash2, Wand2 } from "lucide-react"
import { toast } from "sonner"

import { CleaningStep } from "@/components/cleaning"
import { HighlightedText, MarkLegend, useNow } from "@/components/data"
import { DTYPE_LABEL, DatasetStatus, KIND_LABEL, STAGE_LABEL, TAG_LABEL } from "@/components/dataset"
import { Decisions } from "@/components/decisions"
import { AnswerKeyCheck } from "@/components/detection-extras"
import { NativeSelect } from "@/components/form"
import { LoadError, Loading, useCurrentMembership } from "@/components/org"
import { Chip, InfoTip, InlineError, Num, PageHeader, Spinner, VerdictChip } from "@/components/nz"
import { Button } from "@/components/ui/button"
import { Progress } from "@/components/ui/progress"
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table"
import { ApiError, api, messageFor } from "@/lib/api"
import { KIND_AR, reasonAr } from "@/lib/labels"
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

function H({ children, tip }: { children: React.ReactNode; tip?: React.ReactNode }) {
  return <h2 className="mb-3 flex items-center gap-2 text-lg font-bold">{children}{tip ? <InfoTip>{tip}</InfoTip> : null}</h2>
}

function JobBar({ label, progress }: { label: string; progress: number }) {
  return (
    <div className="rounded-xl border border-border bg-card p-5 shadow-card">
      <div className="mb-3 flex items-center gap-3 font-bold"><Spinner className="size-4 text-primary" /> {label}</div>
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
    return () => { alive = false }
  }, [orgId, ds.id, ds.session_open, i, count])

  if (!count) return null
  return (
    <section>
      <H tip="نفس الملاحظة كما يراها نَظير وكما تراها أداة تقليدية تبحث بأنماط بسيطة، دون تحقق.">داخل النصوص</H>
      <div className="rounded-xl border border-border bg-card shadow-card">
        <div className="flex flex-wrap items-center justify-between gap-3 border-b border-border px-5 py-3">
          <div className="flex items-center gap-1 rounded-lg bg-muted p-1" role="tablist" aria-label="طريقة العرض">
            {(["nazeer", "baseline"] as const).map((v) => (
              <button key={v} role="tab" aria-selected={view === v} onClick={() => setView(v)}
                className={cn("h-8 rounded-md px-3 text-sm font-semibold", view === v ? "bg-card shadow-card" : "text-muted-foreground")}>
                {v === "nazeer"
                  ? <>نَظير <Num>{spans.nazeer_found.toLocaleString("en")}</Num></>
                  : <>أداة تقليدية <Num>{spans.baseline_found.toLocaleString("en")}</Num></>}
              </button>
            ))}
          </div>
          <div className="flex items-center gap-2 text-sm text-muted-foreground">
            <span><Num>{i + 1}</Num> / <Num>{count}</Num></span>
            <Button variant="outline" size="icon-sm" aria-label="السابقة" disabled={i === 0} onClick={() => setI(i - 1)}><ChevronRight /></Button>
            <Button variant="outline" size="icon-sm" aria-label="التالية" disabled={i >= count - 1} onClick={() => setI(i + 1)}><ChevronLeft /></Button>
          </div>
        </div>
        <div className="px-5 py-4">
          {!ds.session_open ? <p className="text-sm text-muted-foreground">حُذفت الأصول.</p>
            : err ? <InlineError>{err}</InlineError>
            : note ? <HighlightedText text={note.text} marks={view === "nazeer" ? note.nazeer : note.baseline} />
            : <Spinner className="size-4" />}
        </div>
        <div className="border-t border-border px-5 py-3"><MarkLegend /></div>
      </div>
    </section>
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
  const [busy, setBusy] = useState(false)
  const [allColumns, setAllColumns] = useState(false)
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
  const idColumns = s?.tables.flatMap((t) => t.columns).filter((c) => c.tag === "DIRECT_ID").length ?? 0
  const found = Object.entries(s?.found_by_type ?? {}).filter(([, n]) => n > 0)
  const minutes = Math.max(0, Math.ceil((new Date(d.session_expires_at + "Z").getTime() - now) / 60000))

  async function generate() {
    setBusy(true)
    try {
      const r = await api<{ job_id: string }>(`/orgs/${orgId}/datasets/${datasetId}/generate`, {
        method: "POST", body: { mode, overrides, target: mode === "synthetic" && target ? target : null },
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
      <PageHeader title={d.name} description={<>رُفعت {formatDateTime(d.created_at)}</>} actions={<DatasetStatus ds={d} now={now} />} />

      {d.session_open && d.status !== "failed" ? (
        <div className="mb-6 flex flex-wrap items-center justify-between gap-3 text-sm text-muted-foreground">
          <span className="flex items-center gap-1.5">
            الأصول تُحذف خلال <Num>{minutes}</Num> د
            <InfoTip>تُحفظ الأصول مشفّرة طوال جلسة المعالجة فقط، ثم تُحذف تلقائياً.</InfoTip>
          </span>
          <Button size="sm" variant="ghost" onClick={endSession}><Trash2 data-icon="inline-start" /> احذف الآن</Button>
        </div>
      ) : null}

      {processing ? (
        <JobBar label={STAGE_LABEL[d.process_job?.stage ?? "reading_files"] ?? "جارٍ المعالجة"} progress={d.process_job?.progress ?? 10} />
      ) : d.status === "failed" ? (
        <InlineError>{messageFor(new ApiError(0, d.error_code ?? "error"))}</InlineError>
      ) : s ? (
        <div className="space-y-10">
          <div className="flex flex-wrap items-center gap-x-3 gap-y-2 rounded-xl border border-border bg-card px-5 py-4 shadow-card">
            <span className="font-bold">ما اكتُشف:</span>
            {found.length ? found.map(([k, n]) => (
              <Chip key={k} tone="sensitive">{KIND_AR[k] ?? "معرّف"} <Num>{n.toLocaleString("en")}</Num></Chip>
            )) : <span className="text-muted-foreground">لا معرّفات مباشرة</span>}
            <span className="ms-auto text-sm text-muted-foreground">
              <Num>{s.total_rows.toLocaleString("en")}</Num> صف · <Num>{s.tables.length}</Num> جدول · <Num>{idColumns}</Num> أعمدة معرّفات
            </span>
          </div>

          <CleaningStep orgId={orgId} ds={d} onApplied={() => void ds.reload()} />

          <Decisions orgId={orgId} dsId={d.id} onChanged={() => void ds.reload()} />

          <section>
            <H tip="ما اكتشفه نَظير في كل عمود. غيّر الإجراء إن لزم، ويُسجَّل كل تعديل في التقرير.">الأعمدة</H>
            {s.tables.map((t) => {
              const cols = allColumns ? t.columns : t.columns.filter((c) => c.tag === "DIRECT_ID" || c.tag === "FREE_TEXT" || c.needs_review)
              return (
                <div key={t.name} className="mb-4 overflow-x-auto rounded-xl border border-border bg-card shadow-card">
                  <div className="flex flex-wrap items-center justify-between gap-2 border-b border-border px-5 py-3">
                    <p className="font-bold"><bdi>{t.name}</bdi></p>
                    <p className="text-sm text-muted-foreground"><Num>{t.rows.toLocaleString("en")}</Num> صف</p>
                  </div>
                  <Table>
                    <TableHeader className="bg-muted/60">
                      <TableRow>
                        <TableHead className="px-5 text-start font-bold">العمود</TableHead>
                        <TableHead className="px-5 text-start font-bold">التصنيف</TableHead>
                        <TableHead className="px-5 text-start font-bold">الإجراء</TableHead>
                      </TableRow>
                    </TableHeader>
                    <TableBody>
                      {cols.map((c) => {
                        const key = `${t.name}.${c.name}`
                        const tag = TAG_LABEL[c.tag]
                        return (
                          <TableRow key={key}>
                            <TableCell className="px-5 py-3 font-semibold"><bdi>{c.name}</bdi></TableCell>
                            <TableCell className="px-5 py-3">
                              <span className="flex flex-wrap items-center gap-1.5">
                                <Chip tone={tag.tone}>{c.kind ? KIND_LABEL[c.kind] ?? tag.label : tag.label}</Chip>
                                {c.needs_review ? <Chip tone="review">للمراجعة</Chip> : null}
                                <InfoTip label={`سبب تصنيف ${c.name}`}>
                                  {reasonAr(c.reason)} · {DTYPE_LABEL[c.dtype] ?? "بيانات"} · ثقة {Math.round(c.confidence * 100)}%
                                </InfoTip>
                              </span>
                            </TableCell>
                            <TableCell className="px-5 py-3">
                              <NativeSelect aria-label={`إجراء العمود ${c.name}`} className="h-9 min-w-40 text-sm"
                                value={choices[key] ?? "auto"} onChange={(e) => setChoices({ ...choices, [key]: e.target.value as Choice })}>
                                <option value="auto">تلقائي</option>
                                <option value="keep">إبقاء</option>
                                <option value="drop">حذف من النظير</option>
                                {Object.entries(KIND_LABEL).map(([k, l]) => <option key={k} value={`pseudo:${k}`}>بديل: {l}</option>)}
                              </NativeSelect>
                            </TableCell>
                          </TableRow>
                        )
                      })}
                    </TableBody>
                  </Table>
                </div>
              )
            })}
            <button type="button" className="text-sm font-semibold text-primary" onClick={() => setAllColumns(!allColumns)}>
              {allColumns ? "المعرّفات فقط" : <>كل الأعمدة (<Num>{s.tables.reduce((n, t) => n + t.columns.length, 0)}</Num>)</>}
            </button>
          </section>

          <NoteViewer orgId={orgId} ds={d} />

          <section>
            <H>النظير</H>
            {generating ? (
              <JobBar label={STAGE_LABEL.generating} progress={d.generate_job?.progress ?? 20} />
            ) : !d.session_open ? (
              <p className="text-sm text-muted-foreground">انتهت الجلسة. ارفع الملفات مجدداً لتوليد نظير جديد.</p>
            ) : (
              <div className="space-y-4 rounded-xl border border-border bg-card p-5 shadow-card">
                <fieldset className="flex flex-wrap gap-3">
                  <legend className="sr-only">نوع النظير</legend>
                  {([
                    ["masked", "مقنّع (موصى به)", "نفس الصفوف، وكل شخص يُستبدل ببديل صالح ومتّسق."],
                    ["synthetic", "اصطناعي · تجريبي", "صفوف جديدة بنفس الأنماط؛ هامش الخصوصية أضيق ويتذبذب."],
                  ] as const).map(([v, title, tip]) => {
                    const disabled = v === "synthetic" && !syntheticAllowed
                    return (
                      <label key={v} className={cn("flex cursor-pointer items-center gap-2 rounded-lg border px-4 py-2.5 text-sm font-semibold",
                        mode === v ? "border-primary bg-accent ring-2 ring-primary/20" : "border-border", disabled && "cursor-not-allowed opacity-60")}>
                        <input type="radio" name="mode" value={v} checked={mode === v} disabled={disabled} onChange={() => setMode(v)} className="sr-only" />
                        {title}
                        <InfoTip>{disabled ? "متاح حتى 15,000 صف في النسخة المستضافة." : tip}</InfoTip>
                      </label>
                    )
                  })}
                </fieldset>
                {mode === "synthetic" ? (
                  <div className="max-w-md">
                    <NativeSelect id="target" aria-label="عمود اختبار الفائدة (اختياري)" value={target} onChange={(e) => setTarget(e.target.value)}>
                      <option value="">بلا اختبار فائدة</option>
                      {s.tables.flatMap((t) => t.columns.filter((c) => c.dtype === "numeric" && c.tag !== "DIRECT_ID")
                        .map((c) => <option key={`${t.name}.${c.name}`} value={`high_${c.name}=${c.name}>p90`}>أعلى 10% في {c.name}</option>))}
                      {s.tables.flatMap((t) => t.columns.filter((c) => c.dtype === "categorical" && c.unique === 2)
                        .map((c) => <option key={`b${t.name}.${c.name}`} value={c.name}>{c.name}</option>))}
                    </NativeSelect>
                  </div>
                ) : null}
                <div className="flex flex-wrap items-center gap-3">
                  <Button size="lg" onClick={generate} disabled={busy || membership === undefined}>
                    {busy ? <Spinner className="size-4" /> : <Wand2 data-icon="inline-start" />} ولّد النظير
                  </Button>
                  {Object.keys(overrides).length ? (
                    <span className="text-sm text-muted-foreground"><Num>{Object.keys(overrides).length}</Num> تعديل يدوي</span>
                  ) : null}
                </div>
              </div>
            )}
          </section>

          <AnswerKeyCheck orgId={orgId} ds={d} />

          {d.twins.length ? (
            <section>
              <H>النظائر</H>
              <ul className="divide-y divide-border rounded-xl border border-border bg-card shadow-card">
                {d.twins.map((t) => (
                  <li key={t.id}>
                    <Link href={`/app/o/${orgId}/twins/${t.id}`} className="flex flex-wrap items-center justify-between gap-3 px-5 py-4 hover:bg-muted/50">
                      <span className="flex items-center gap-3 font-semibold">
                        <FileCheck2 className="size-4 text-muted-foreground" aria-hidden="true" />
                        {t.mode === "masked" ? "مقنّع" : "اصطناعي"}
                        <span className="text-sm font-normal text-muted-foreground">{formatDateTime(t.created_at)}</span>
                      </span>
                      <VerdictChip verdict={t.verdict} />
                    </Link>
                  </li>
                ))}
              </ul>
            </section>
          ) : null}
        </div>
      ) : null}
    </>
  )
}
