"use client"

import { useEffect, useState } from "react"
import { AlertTriangle, Download, KeyRound, Link2, Send } from "lucide-react"
import { toast } from "sonner"

import { FileDropzone, minutesLeft, useNow } from "@/components/data"
import { Chip, InfoTip, InlineError, Notice, Num, Section, Spinner } from "@/components/nz"
import { Button } from "@/components/ui/button"
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog"
import { ApiError, messageFor, upload } from "@/lib/api"
import type { Received, ReturnCounts, ReturnInfo, ReturnReport } from "@/lib/types"
import { formatDateTime, useApi } from "@/lib/use-api"
import { cn } from "@/lib/utils"

const ACCEPT = ".xlsx,.csv,.tsv,.txt,text/csv,application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"

export const TOKEN_RULE = "لا تحذف عمود رمز_التحقق ولا تعدّله؛ أضف نتائجك في أعمدة جديدة."
export const TOKEN_RULE_MORE = "يمكنك حذف صفوف وإرجاع جزء من البيانات فقط."

const STATUS_TILES: { key: keyof ReturnCounts; label: string; tone: string; hint: string }[] = [
  { key: "verified", label: "مُتحقَّق", tone: "text-twin", hint: "رمزه صحيح ومن هذه المشاركة" },
  { key: "invalid", label: "غير صالح", tone: "text-sensitive", hint: "رمز موجود لكنه مُعدَّل أو تالف" },
  { key: "missing", label: "بلا رمز", tone: "text-review", hint: "خلية الرمز فارغة" },
  { key: "foreign", label: "غريب", tone: "text-sensitive", hint: "رمز من مشاركة أو منشأة أخرى" },
  { key: "duplicate", label: "مكرر", tone: "text-review", hint: "الرمز نفسه ورد أكثر من مرة" },
]

function pct(x: number | null | undefined, digits = 1) {
  if (x == null) return "—"
  return `${(x * 100).toFixed(x === 1 || x === 0 ? 0 : digits)}%`
}

/** The verification report: large numbers first, details below. */
export function VerificationReport({ report, compact = false }: { report: ReturnReport; compact?: boolean }) {
  const c = report.counts
  const added = Object.values(report.added_columns).flat()
  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-end gap-x-8 gap-y-3">
        <div>
          <p className="text-sm text-muted-foreground">سلامة الصفوف</p>
          <p className={cn("text-4xl font-bold", report.integrity === 1 ? "text-twin" : "text-review")}><Num>{pct(report.integrity)}</Num></p>
        </div>
        <div>
          <p className="text-sm text-muted-foreground">صفوف مُعادة</p>
          <p className="text-2xl font-bold"><Num>{report.rows_returned.toLocaleString("en")}</Num></p>
        </div>
        <div>
          <p className="text-sm text-muted-foreground">التغطية (من المشارَك)</p>
          <p className="text-2xl font-bold"><Num>{pct(report.coverage, 2)}</Num></p>
        </div>
      </div>
      <div className="grid grid-cols-2 gap-3 sm:grid-cols-5">
        {STATUS_TILES.map((t) => (
          <div key={t.key} className="rounded-xl border border-border bg-card px-4 py-3 shadow-card">
            <p className="text-sm font-semibold text-muted-foreground">{t.label}</p>
            <p className={cn("text-3xl font-bold", c[t.key] ? t.tone : "text-muted-foreground")}><Num>{c[t.key].toLocaleString("en")}</Num></p>
            {!compact ? <p className="mt-1 text-xs text-muted-foreground">{t.hint}</p> : null}
          </div>
        ))}
      </div>
      {c.old_key ? (
        <Notice tone="review" icon={AlertTriangle}>
          لا يمكن التحقق من <Num>{c.old_key}</Num> صف: صُنع بمفتاح سابق (غُيّر مفتاح المنشأة بعد المشاركة).
        </Notice>
      ) : null}
      {!compact ? (
        <div className="space-y-1 text-sm leading-7">
          {added.length ? (
            <p>أعمدة أضافها المستلم: {added.map((a) => <bdi key={a} className="me-1 rounded bg-muted px-1.5">{a}</bdi>)}</p>
          ) : <p className="text-muted-foreground">لم يُضف المستلم أعمدة جديدة.</p>}
          {(["invalid", "missing", "foreign", "duplicate"] as const).map((k) =>
            report.rows_by_status[k]?.length ? (
              <p key={k} className="text-muted-foreground">
                {STATUS_TILES.find((t) => t.key === k)!.label}: الصفوف <Num>{report.rows_by_status[k]!.slice(0, 30).join("، ")}</Num>
                {report.rows_by_status[k]!.length > 30 ? " …" : ""}
              </p>
            ) : null,
          )}
          <p className="text-muted-foreground">
            للعلم فقط: <Num>{report.rows_changed_in_twin_columns.toLocaleString("en")}</Num> صفاً غيّر المستلم فيها قيماً في أعمدة
            النظير. تُتجاهل هذه القيم: البيانات الأصلية تأتي من ملف المنشأة.
          </p>
        </div>
      ) : null}
    </div>
  )
}

/** Recipient side: send results back for this share. */
export function ReturnResults({ share }: { share: Received }) {
  const info = share.returns
  const mine = useApi<ReturnInfo[]>(info ? `/received/${share.id}/returns` : null)
  const [files, setFiles] = useState<File[]>([])
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<ApiError | null>(null)
  const [last, setLast] = useState<ReturnInfo | null>(null)
  if (!info) return null

  async function send() {
    setBusy(true)
    setError(null)
    try {
      const form = new FormData()
      form.append("files", files[0])
      const r = await upload<ReturnInfo>(`/received/${share.id}/returns`, form)
      setLast(r)
      toast.success(`استُلمت النتائج: ${r.verified.toLocaleString("en")} صف مُتحقَّق.`)
      setFiles([])
      await mine.reload()
    } catch (e) {
      setError(e instanceof ApiError ? e : new ApiError(0, "error"))
    } finally {
      setBusy(false)
    }
  }

  return (
    <Section title="أعد النتائج">
      <div className="space-y-4 rounded-xl border border-border bg-card p-5 shadow-card">
        <p className="flex items-center gap-1.5 text-sm font-semibold"><KeyRound className="size-4 text-primary" aria-hidden="true" />{TOKEN_RULE}<InfoTip>{TOKEN_RULE_MORE} ملف Excel أو CSV.</InfoTip></p>
        <FileDropzone files={files} onChange={(f) => setFiles(f.slice(-1))} accept={ACCEPT} />
        {error ? <InlineError>{messageFor(error)}</InlineError> : null}
        <Button onClick={send} disabled={!files.length || busy}>
          {busy ? <Spinner className="size-4" /> : <Send data-icon="inline-start" />}
          إرسال النتائج
        </Button>
        {last ? <VerificationReport report={last.report} compact /> : null}
      </div>
      {mine.data?.length ? (
        <ul className="divide-y divide-border rounded-xl border border-border bg-card shadow-card">
          {mine.data.map((r) => (
            <li key={r.id} className="flex flex-wrap items-center justify-between gap-3 px-5 py-3 text-sm">
              <span>
                <bdi className="font-semibold">{r.file_name}</bdi>
                <span className="ms-2 text-muted-foreground">{formatDateTime(r.created_at)}</span>
              </span>
              <span className="flex flex-wrap items-center gap-2">
                <Chip tone={r.report.integrity === 1 ? "twin" : "review"}>سلامة <Num>{pct(r.report.integrity)}</Num></Chip>
                <Chip tone="neutral"><Num>{r.verified.toLocaleString("en")}</Num> من <Num>{r.rows_returned.toLocaleString("en")}</Num> مُتحقَّق</Chip>
              </span>
            </li>
          ))}
        </ul>
      ) : null}
    </Section>
  )
}

/** Organization side: re-link one return (admins only). */
export function RelinkDialog({ orgId, returnId, open, onOpenChange, onChanged }: {
  orgId: string
  returnId: string | null
  open: boolean
  onOpenChange: (o: boolean) => void
  onChanged: () => void
}) {
  const detail = useApi<ReturnInfo>(open && returnId ? `/orgs/${orgId}/returns/${returnId}` : null)
  const [files, setFiles] = useState<File[]>([])
  const [confirm, setConfirm] = useState(false)
  const [busy, setBusy] = useState(false)
  const now = useNow(5000)
  const d = detail.data
  const running = d?.relink?.status === "running"

  useEffect(() => {
    if (!running) return
    const t = setInterval(() => void detail.reload(), 2000)
    return () => clearInterval(t)
  }, [running, detail])
  useEffect(() => {
    if (d?.relink?.status && d.relink.status !== "running") onChanged()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [d?.relink?.status])

  const partial = (d?.report.integrity ?? 1) < 1

  async function start() {
    setBusy(true)
    try {
      const form = new FormData()
      for (const f of files) form.append("files", f)
      form.append("confirm_partial", confirm ? "true" : "false")
      await upload(`/orgs/${orgId}/returns/${returnId}/relink`, form)
      setFiles([])
      await detail.reload()
    } catch (e) {
      toast.error(messageFor(e))
    } finally {
      setBusy(false)
    }
  }

  const rl = d?.relink
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-h-[90vh] overflow-y-auto sm:max-w-2xl">
        <DialogHeader>
          <DialogTitle className="text-lg">إعادة الربط بالسجلات الحقيقية</DialogTitle>
          <DialogDescription>
            يفكّ نَظير رموز التحقق بمفتاح المنشأة في الذاكرة ويطابقها مع ملفك الأصلي، ثم يُحذف كل شيء. لا يُحفظ أي جدول ربط.
          </DialogDescription>
        </DialogHeader>
        {!d ? (
          <Spinner className="size-4" />
        ) : (
          <div className="space-y-5">
            <VerificationReport report={d.report} compact />
            {rl?.status === "ready" && rl.expires_at ? (
              <div className="space-y-3 rounded-xl border border-twin/25 bg-twin-soft p-4">
                <p className="font-bold text-twin">رُبط <Num>{(rl.matched ?? 0).toLocaleString("en")}</Num> صف بسجلاته الحقيقية.</p>
                {rl.mine ? (
                  <>
                    <p className="text-sm">الملف متاح لك وحدك ويُحذف خلال <Num>{minutesLeft(rl.expires_at, now)}</Num> دقيقة. كل تنزيل يُسجَّل.</p>
                    <div className="flex flex-wrap gap-2">
                      <Button render={<a href={`/api/orgs/${orgId}/returns/${d.id}/relinked.xlsx`} />} nativeButton={false}>
                        <Download data-icon="inline-start" /> تنزيل Excel
                      </Button>
                      <Button variant="outline" render={<a href={`/api/orgs/${orgId}/returns/${d.id}/relinked.csv`} />} nativeButton={false}>
                        <Download data-icon="inline-start" /> تنزيل CSV
                      </Button>
                    </div>
                  </>
                ) : (
                  <p className="text-sm">الملف متاح للمدير الذي طلب الربط فقط.</p>
                )}
              </div>
            ) : running ? (
              <div className="flex items-center gap-3 rounded-xl border border-border p-4 font-semibold">
                <Spinner className="size-4 text-primary" /> يفكّ نَظير الرموز ويطابقها مع ملفك…
              </div>
            ) : !d.relinkable ? (
              <InlineError>
                {d.report.counts.verified ? "انتهت مدة الاحتفاظ بهذه النتائج." : "لا يوجد صف مُتحقَّق في هذا الملف، فلا يمكن إعادة الربط."}
              </InlineError>
            ) : (
              <>
                {rl?.status === "failed" && rl.error_code ? <InlineError>{messageFor(new ApiError(0, rl.error_code))}</InlineError> : null}
                {rl?.status === "expired" ? <Notice>انتهت مدة الملف السابق وحُذف.</Notice> : null}
                <Notice>
                  ارفع ملفك الأصلي{d.source_tables?.length ? (
                    <> ({d.source_tables.map((t, i) => (
                      <span key={t.name}>{i ? "، " : ""}<bdi>{t.name}</bdi>{t.key_column ? <> بعمود <bdi>{t.key_column}</bdi></> : " بالترتيب نفسه"}</span>
                    ))})</>
                  ) : null}. يمكن أن يكون أكبر من الجزء المُعاد أو أصغر منه: يُربط ما يطابق فقط.
                </Notice>
                <FileDropzone files={files} onChange={setFiles} accept={ACCEPT} />
                {partial ? (
                  <label className="flex items-start gap-3 rounded-xl border border-review/30 bg-review-soft p-4 text-sm text-review">
                    <input type="checkbox" className="mt-1 size-4" checked={confirm} onChange={(e) => setConfirm(e.target.checked)} />
                    <span>
                      سلامة الصفوف <Num>{pct(d.report.integrity)}</Num> أقل من 100%. سيُربط <Num>{d.report.counts.verified}</Num> صف
                      مُتحقَّق فقط وتُستبعد البقية. أؤكد المتابعة (يُسجَّل في سجل التدقيق).
                    </span>
                  </label>
                ) : null}
              </>
            )}
          </div>
        )}
        <DialogFooter>
          {d && d.relinkable && !running && !(rl?.status === "ready" && rl.expires_at) ? (
            <Button onClick={start} disabled={!files.length || busy || (partial && !confirm)}>
              {busy ? <Spinner className="size-4" /> : <Link2 data-icon="inline-start" />}
              ابدأ إعادة الربط
            </Button>
          ) : null}
          <Button variant="outline" onClick={() => onOpenChange(false)}>إغلاق</Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
