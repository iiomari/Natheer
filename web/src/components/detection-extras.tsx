"use client"

import { useState } from "react"
import { ClipboardCheck, FileSearch } from "lucide-react"

import { FileDropzone } from "@/components/data"
import { Chip, InlineError, Notice, Num, Section, Spinner } from "@/components/nz"
import { Button } from "@/components/ui/button"
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table"
import { ApiError, messageFor, upload } from "@/lib/api"
import { KIND_AR } from "@/lib/labels"
import type { Dataset } from "@/lib/types"
import { useApi } from "@/lib/use-api"

/** What was found, by type, in one line of chips. */
export function FoundByType({ ds }: { ds: Dataset }) {
  const found = ds.summary?.found_by_type ?? {}
  const entries = Object.entries(found).filter(([, n]) => n > 0)
  if (!entries.length) return <Notice>لم يُعثر على بيانات شخصية مباشرة في هذه الملفات.</Notice>
  return (
    <div className="flex flex-wrap items-center gap-2 rounded-xl border border-border bg-card px-5 py-4 shadow-card">
      <span className="font-bold">ما اكتُشف:</span>
      {entries.map(([k, n]) => (
        <Chip key={k} tone="sensitive">
          {KIND_AR[k] ?? "معرّف"} <Num>{n.toLocaleString("en")}</Num>
        </Chip>
      ))}
      {ds.summary?.review?.total ? (
        <Chip tone="review">للمراجعة <Num>{ds.summary.review.total.toLocaleString("en")}</Num></Chip>
      ) : null}
    </div>
  )
}

type ReviewItem = { table: string; column: string; row: number; kind: string; text: string; start: number; end: number }

/** The uncertain values, highlighted in their sentence (original text: session only). */
export function ReviewQueue({ orgId, ds }: { orgId: string; ds: Dataset }) {
  const total = ds.summary?.review?.total ?? 0
  const r = useApi<{ total: number; items: ReviewItem[] }>(total && ds.session_open ? `/orgs/${orgId}/datasets/${ds.id}/review` : null)
  if (!total) return null
  return (
    <Section
      title={`قيم للمراجعة (${total.toLocaleString("en")})`}
      description="أرقام تجتاز التحقق الرسمي لكنها جاءت في سياق لا يدل على شخص (مثل «رقم الطلب»). تُترك كما هي في النظير ما لم توافق على استبدالها."
    >
      {!ds.session_open ? (
        <Notice>حُذفت الأصول، فلا يمكن عرض الأمثلة.</Notice>
      ) : r.loading ? (
        <Spinner className="size-4" />
      ) : r.error ? (
        <InlineError>{messageFor(r.error)}</InlineError>
      ) : (
        <ul className="divide-y divide-border rounded-xl border border-border bg-card shadow-card">
          {r.data?.items.map((it, i) => (
            <li key={i} className="flex flex-wrap items-center gap-3 px-5 py-3 text-sm">
              <Chip tone="review">{KIND_AR[it.kind] ?? "معرّف"}؟</Chip>
              <span className="min-w-0 flex-1 leading-7">
                {it.text.slice(0, it.start)}
                <mark className="rounded bg-review-soft px-1 font-semibold text-review">{it.text.slice(it.start, it.end)}</mark>
                {it.text.slice(it.end)}
              </span>
              <span className="text-xs text-muted-foreground"><bdi>{it.column}</bdi> · صف <Num>{it.row}</Num></span>
            </li>
          ))}
        </ul>
      )}
    </Section>
  )
}

type KeyResult = {
  types: Record<string, { planted: number; found: number; missed: number; not_located: number; recall: number | null }>
  look_alikes: { total: number; ignored: number; review: number; wrong: number; not_located: number }
}

/** Optional independent proof: the user's own answer key against what Nazeer found. */
export function AnswerKeyCheck({ orgId, ds }: { orgId: string; ds: Dataset }) {
  const [open, setOpen] = useState(false)
  const [files, setFiles] = useState<File[]>([])
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [res, setRes] = useState<KeyResult | null>(null)
  if (!ds.session_open) return null

  async function run() {
    setBusy(true)
    setError(null)
    try {
      const form = new FormData()
      form.append("file", files[0])
      setRes(await upload<KeyResult>(`/orgs/${orgId}/datasets/${ds.id}/answer-key`, form))
    } catch (e) {
      setError(messageFor(e instanceof ApiError ? e : new ApiError(0, "error")))
    } finally {
      setBusy(false)
    }
  }

  return (
    <Section title="تحقق مستقل بمفتاح إجابة (اختياري)"
      description="إن كان لديك ملف يذكر القيم الشخصية المزروعة في بياناتك، ارفعه لترى ما وجده نَظير وما فاته. لا يُحفظ الملف.">
      {!open ? (
        <Button variant="outline" onClick={() => setOpen(true)}>
          <FileSearch data-icon="inline-start" /> رفع مفتاح إجابة
        </Button>
      ) : (
        <div className="space-y-4 rounded-xl border border-border bg-card p-5 shadow-card">
          <p className="text-sm text-muted-foreground">
            ملف CSV بأعمدة: الصف، معرّف السجل، العمود، النوع، القيمة المزروعة، المتوقع (استبدال / مراجعة / تجاهل).
          </p>
          <FileDropzone files={files} onChange={(f) => setFiles(f.slice(-1))} accept=".csv,text/csv" />
          {error ? <InlineError>{error}</InlineError> : null}
          <Button onClick={run} disabled={!files.length || busy}>
            {busy ? <Spinner className="size-4" /> : <ClipboardCheck data-icon="inline-start" />} قارن
          </Button>
          {res ? (
            <div className="space-y-4">
              <div className="overflow-x-auto rounded-lg border border-border">
                <Table>
                  <TableHeader className="bg-muted/60">
                    <TableRow>
                      <TableHead className="px-4 text-start font-bold">النوع</TableHead>
                      <TableHead className="px-4 text-start font-bold">مزروع</TableHead>
                      <TableHead className="px-4 text-start font-bold">وجده نَظير</TableHead>
                      <TableHead className="px-4 text-start font-bold">فاته</TableHead>
                      <TableHead className="px-4 text-start font-bold">النسبة</TableHead>
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {Object.entries(res.types).map(([k, v]) => (
                      <TableRow key={k}>
                        <TableCell className="px-4 py-2 font-semibold">{KIND_AR[k] ?? "معرّف"}</TableCell>
                        <TableCell className="px-4 py-2"><Num>{v.planted.toLocaleString("en")}</Num></TableCell>
                        <TableCell className="px-4 py-2 text-twin"><Num>{v.found.toLocaleString("en")}</Num></TableCell>
                        <TableCell className="px-4 py-2"><Num>{v.missed.toLocaleString("en")}</Num></TableCell>
                        <TableCell className="px-4 py-2 font-bold">
                          {v.recall == null ? "—" : <Num>{`${(v.recall * 100).toFixed(1)}%`}</Num>}
                        </TableCell>
                      </TableRow>
                    ))}
                  </TableBody>
                </Table>
              </div>
              {res.look_alikes.total ? (
                <p className="text-sm leading-7">
                  أرقام مشابهة ليست معرّفات: <Num>{res.look_alikes.total}</Num> · تجاهلها نَظير بحق <Num>{res.look_alikes.ignored}</Num> ·
                  أرسلها للمراجعة <Num>{res.look_alikes.review}</Num> · عاملها خطأً كمعرّف <Num>{res.look_alikes.wrong}</Num>
                </p>
              ) : null}
            </div>
          ) : null}
        </div>
      )}
    </Section>
  )
}
