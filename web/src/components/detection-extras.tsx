"use client"

import { useState } from "react"
import { ClipboardCheck, FileSearch } from "lucide-react"

import { FileDropzone } from "@/components/data"
import { InfoTip, InlineError, Num, Spinner } from "@/components/nz"
import { Button } from "@/components/ui/button"
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table"
import { ApiError, messageFor, upload } from "@/lib/api"
import { KIND_AR } from "@/lib/labels"
import type { Dataset } from "@/lib/types"

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
    <section aria-label="مفتاح الإجابة">
      {!open ? (
        <span className="flex items-center gap-1">
          <Button variant="ghost" size="sm" onClick={() => setOpen(true)}>
            <FileSearch data-icon="inline-start" /> تحقق بمفتاح إجابة
          </Button>
          <InfoTip>اختياري: ارفع ملفاً يذكر القيم المزروعة لترى ما وجده نَظير وما فاته. لا يُحفظ الملف.</InfoTip>
        </span>
      ) : (
        <div className="space-y-4 rounded-xl border border-border bg-card p-5 shadow-card">
          <p className="flex items-center gap-1 font-bold">مفتاح الإجابة
            <InfoTip>ملف CSV بأعمدة: الصف، معرّف السجل، العمود، النوع، القيمة المزروعة، المتوقع (استبدال / مراجعة / تجاهل).</InfoTip>
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
                  أرقام مشابهة: <Num>{res.look_alikes.total}</Num> · تجاهلها <Num>{res.look_alikes.ignored}</Num> ·
                  حُسمت بدليل <Num>{res.look_alikes.review}</Num> · خطأ <Num>{res.look_alikes.wrong}</Num>
                </p>
              ) : null}
            </div>
          ) : null}
        </div>
      )}
    </section>
  )
}
