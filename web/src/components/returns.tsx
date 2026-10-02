"use client"

import { useEffect, useState } from "react"
import { Download, Link2, Send, ShieldAlert } from "lucide-react"
import { toast } from "sonner"

import { FileDropzone, minutesLeft, useNow } from "@/components/data"
import { Chip, InlineError, Ltr, Notice, Num, Section, Spinner } from "@/components/nz"
import { Button } from "@/components/ui/button"
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog"
import { ApiError, messageFor, upload } from "@/lib/api"
import type { Received, ReturnInfo, ReturnRejected } from "@/lib/types"
import { formatDateTime, useApi } from "@/lib/use-api"

const ACCEPT = ".csv,.tsv,.txt,.xlsx,text/csv,application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"

const REJECT_LABEL: Record<keyof ReturnRejected, string> = {
  ref_mismatch: "مفتاح لا يطابق مرجعه",
  unknown_key: "مفتاح غير موجود في البيانات",
  missing_key: "مفتاح فارغ",
  duplicate_key: "مفتاح مكرر",
}

export function RejectedCounts({ rejected }: { rejected: Partial<ReturnRejected> | undefined }) {
  const items = Object.entries(rejected ?? {}).filter(([, n]) => (n ?? 0) > 0) as [keyof ReturnRejected, number][]
  if (!items.length) return <span className="text-muted-foreground">لا صفوف مرفوضة</span>
  return (
    <span className="flex flex-wrap gap-1.5">
      {items.map(([k, n]) => (
        <Chip key={k} tone={k === "ref_mismatch" ? "sensitive" : "review"}>
          {REJECT_LABEL[k]}: <Num>{n.toLocaleString("en")}</Num>
        </Chip>
      ))}
    </span>
  )
}

/** Recipient side: send results back for this share. */
export function ReturnResults({ share }: { share: Received }) {
  const info = share.returns
  const mine = useApi<ReturnInfo[]>(info ? `/received/${share.id}/returns` : null)
  const [files, setFiles] = useState<File[]>([])
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<ApiError | null>(null)
  if (!info) return null

  async function send() {
    setBusy(true)
    setError(null)
    try {
      const form = new FormData()
      form.append("files", files[0])
      const r = await upload<ReturnInfo>(`/received/${share.id}/returns`, form)
      toast.success(`استُلمت النتائج: ${r.rows_accepted.toLocaleString("en")} صف مقبول.`)
      setFiles([])
      await mine.reload()
    } catch (e) {
      setError(e instanceof ApiError ? e : new ApiError(0, "error"))
    } finally {
      setBusy(false)
    }
  }

  return (
    <Section title="إعادة النتائج إلى المنشأة" description="بعد عملك على البيانات، أعد ملف نتائجك لتربطه المنشأة بسجلاتها الحقيقية.">
      <div className="space-y-4 rounded-xl border border-border bg-card p-5 shadow-card">
        <Notice>
          ملف واحد (CSV أو Excel) فيه عمودا <Ltr>{info.column}</Ltr> و<Ltr>{info.ref_column}</Ltr> كما نزلا من جدول{" "}
          <Ltr>{info.table}</Ltr> دون تعديل، وأي أعمدة نتائج تضيفها. يُرفض الملف إن لم يطابق المفتاح مرجعه في أكثر من 1% من الصفوف.
        </Notice>
        <FileDropzone files={files} onChange={(f) => setFiles(f.slice(-1))} accept={ACCEPT} />
        {error ? (
          <div className="space-y-2">
            <InlineError>{messageFor(error)}</InlineError>
            {error.detail?.rejected ? (
              <p className="text-sm">
                من <Num>{Number(error.detail.rows_total ?? 0).toLocaleString("en")}</Num> صف:{" "}
                <RejectedCounts rejected={error.detail.rejected as ReturnRejected} />
              </p>
            ) : null}
          </div>
        ) : null}
        <Button onClick={send} disabled={!files.length || busy}>
          {busy ? <Spinner className="size-4" /> : <Send data-icon="inline-start" />}
          إرسال النتائج
        </Button>
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
                <Chip tone="twin"><Num>{r.rows_accepted.toLocaleString("en")}</Num> صف مقبول</Chip>
                <RejectedCounts rejected={r.rejected} />
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

  async function start() {
    setBusy(true)
    try {
      const form = new FormData()
      for (const f of files) form.append("files", f)
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
      <DialogContent className="max-h-[90vh] overflow-y-auto sm:max-w-xl">
        <DialogHeader>
          <DialogTitle className="text-lg">إعادة الربط بالسجلات الحقيقية</DialogTitle>
          <DialogDescription>
            لا يحتفظ نَظير بأي جدول ربط. ارفع الملفات الأصلية نفسها التي صُنع منها النظير، فيعيد حساب الأسماء المستعارة بمفتاح
            المنشأة في الذاكرة ويطابقها، ثم يُحذف كل شيء.
          </DialogDescription>
        </DialogHeader>
        {!d ? (
          <Spinner className="size-4" />
        ) : (
          <div className="space-y-4">
            <p className="text-sm">
              <bdi className="font-semibold">{d.file_name}</bdi> · <Num>{d.rows_accepted.toLocaleString("en")}</Num> صف · عمود
              الربط <Ltr>{d.link?.column}</Ltr>
            </p>
            {rl?.status === "ready" && rl.expires_at ? (
              <div className="space-y-3 rounded-xl border border-twin/25 bg-twin-soft p-4">
                <p className="font-bold text-twin">
                  رُبط <Num>{(rl.matched ?? 0).toLocaleString("en")}</Num> صف بسجلاته الحقيقية.
                </p>
                {rl.mine ? (
                  <>
                    <p className="text-sm">
                      الملف متاح لك وحدك ويُحذف خلال <Num>{minutesLeft(rl.expires_at, now)}</Num> دقيقة. كل تنزيل يُسجَّل.
                    </p>
                    <div className="flex flex-wrap gap-2">
                      <Button render={<a href={`/api/orgs/${orgId}/returns/${d.id}/relinked.csv`} />} nativeButton={false}>
                        <Download data-icon="inline-start" /> تنزيل CSV
                      </Button>
                      <Button variant="outline" render={<a href={`/api/orgs/${orgId}/returns/${d.id}/relinked.xlsx`} />} nativeButton={false}>
                        <Download data-icon="inline-start" /> تنزيل Excel
                      </Button>
                    </div>
                  </>
                ) : (
                  <p className="text-sm">الملف متاح للمدير الذي طلب الربط فقط.</p>
                )}
              </div>
            ) : running ? (
              <div className="flex items-center gap-3 rounded-xl border border-border p-4 font-semibold">
                <Spinner className="size-4 text-primary" /> يعيد نَظير الحساب ويطابق المفاتيح…
              </div>
            ) : (
              <>
                {rl?.status === "failed" && rl.error_code ? (
                  <InlineError>{messageFor(new ApiError(0, rl.error_code))}</InlineError>
                ) : null}
                {rl?.status === "expired" ? <Notice>انتهت مدة الملف السابق وحُذف.</Notice> : null}
                <Notice tone="review" icon={ShieldAlert}>
                  ارفع الملفات نفسها بأسمائها ({d.source_tables?.map((t, i) => <Ltr key={t}>{i ? "، " : ""}{t}</Ltr>)}) دون إضافة
                  صفوف أو حذفها: أي اختلاف يغيّر الأسماء المستعارة فيُرفض الربط.
                </Notice>
                <FileDropzone files={files} onChange={setFiles} accept={ACCEPT} />
              </>
            )}
          </div>
        )}
        <DialogFooter>
          {d && !running && !(rl?.status === "ready" && rl.expires_at) ? (
            <Button onClick={start} disabled={!files.length || busy}>
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
