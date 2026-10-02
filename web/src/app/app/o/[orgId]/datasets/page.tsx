"use client"

import Link from "next/link"
import { useRouter } from "next/navigation"
import { useState } from "react"
import { Database, Info, Upload } from "lucide-react"

import { FileDropzone, useNow } from "@/components/data"
import { DatasetStatus } from "@/components/dataset"
import { TextField } from "@/components/form"
import { LoadError, Loading, useCurrentMembership } from "@/components/org"
import { EmptyState, InlineError, Notice, Num, PageHeader, Spinner, VerdictChip } from "@/components/nz"
import { Button } from "@/components/ui/button"
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog"
import { messageFor, upload } from "@/lib/api"
import type { Dataset } from "@/lib/types"
import { formatDateTime, useApi } from "@/lib/use-api"

const ACCEPT = ".csv,.tsv,.txt,.xlsx,.xlsm,text/csv,application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"

function UploadDialog({ orgId, open, onOpenChange }: { orgId: string; open: boolean; onOpenChange: (v: boolean) => void }) {
  const router = useRouter()
  const [files, setFiles] = useState<File[]>([])
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)

  async function onSubmit(e: React.FormEvent<HTMLFormElement>) {
    e.preventDefault()
    if (!files.length) return setError("اختر ملفاً واحداً على الأقل.")
    const form = new FormData()
    form.set("name", String(new FormData(e.currentTarget).get("name") ?? ""))
    files.forEach((f) => form.append("files", f, f.name))
    setBusy(true)
    setError(null)
    try {
      const ds = await upload<Dataset>(`/orgs/${orgId}/datasets`, form)
      router.push(`/app/o/${orgId}/datasets/${ds.id}`)
    } catch (err) {
      setError(messageFor(err))
      setBusy(false)
    }
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-xl">
        <DialogHeader>
          <DialogTitle className="text-lg">رفع بيانات</DialogTitle>
          <DialogDescription>ملف واحد أو عدة ملفات مترابطة. كل ورقة في Excel تُعامل كجدول.</DialogDescription>
        </DialogHeader>
        <form id="upload-form" onSubmit={onSubmit} className="space-y-5" noValidate>
          <Notice icon={Info}>يُرجى استخدام بيانات تجريبية في هذه النسخة.</Notice>
          {error ? <InlineError>{error}</InlineError> : null}
          <TextField name="name" label="اسم مجموعة البيانات (اختياري)" placeholder="مثال: مطالبات الربع الأول" />
          <FileDropzone files={files} onChange={setFiles} accept={ACCEPT} />
          <p className="text-xs leading-5 text-muted-foreground">
            تُحفظ الملفات الأصلية مشفّرة مدة جلسة المعالجة فقط (<Num>30</Num> دقيقة)، ثم تُحذف تلقائياً.
          </p>
        </form>
        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)}>إلغاء</Button>
          <Button type="submit" form="upload-form" disabled={busy || !files.length}>
            {busy ? <Spinner className="size-4" /> : <Upload data-icon="inline-start" />}
            رفع ومعالجة
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}

export default function DatasetsPage() {
  const { orgId, membership } = useCurrentMembership()
  const canManage = membership?.role === "admin" || membership?.data_manager
  const list = useApi<Dataset[]>(canManage ? `/orgs/${orgId}/datasets` : null)
  const [open, setOpen] = useState(false)
  const now = useNow()

  return (
    <>
      <PageHeader
        title="مجموعات البيانات"
        description="ارفع جداولك، راجع ما اكتُشف، ثم ولّد النظير."
        actions={
          canManage ? (
            <Button onClick={() => setOpen(true)}>
              <Upload data-icon="inline-start" />
              رفع بيانات
            </Button>
          ) : null
        }
      />
      {!canManage ? (
        <EmptyState icon={Database} title="هذه الصفحة للمدير ومدير البيانات" />
      ) : list.loading ? (
        <Loading />
      ) : list.error ? (
        <LoadError error={list.error} />
      ) : !list.data?.length ? (
        <EmptyState
          icon={Database}
          title="لا توجد مجموعات بيانات بعد"
          description="ارفع ملف CSV أو Excel لتبدأ. يتعرّف نَظير على الترميز والفواصل والعناوين تلقائياً."
          action={<Button onClick={() => setOpen(true)}><Upload data-icon="inline-start" />رفع بيانات</Button>}
        />
      ) : (
        <ul className="grid gap-4">
          {list.data.map((ds) => (
            <li key={ds.id}>
              <Link
                href={`/app/o/${orgId}/datasets/${ds.id}`}
                className="flex flex-wrap items-center justify-between gap-4 rounded-xl border border-border bg-card p-5 shadow-card transition-colors hover:border-primary/40"
              >
                <div className="min-w-0">
                  <p className="truncate text-lg font-bold">{ds.name}</p>
                  <p className="mt-1 text-sm text-muted-foreground">
                    {ds.tables.length ? (
                      <>
                        <Num>{ds.tables.length}</Num> جداول · <Num>{ds.tables.reduce((a, t) => a + t.rows, 0).toLocaleString("en")}</Num> صف ·{" "}
                      </>
                    ) : null}
                    {formatDateTime(ds.created_at)}
                  </p>
                </div>
                <div className="flex flex-wrap items-center gap-2">
                  {ds.twins[0] ? <VerdictChip verdict={ds.twins[0].verdict} /> : null}
                  <DatasetStatus ds={ds} now={now} />
                </div>
              </Link>
            </li>
          ))}
        </ul>
      )}
      <UploadDialog orgId={orgId} open={open} onOpenChange={setOpen} />
    </>
  )
}
