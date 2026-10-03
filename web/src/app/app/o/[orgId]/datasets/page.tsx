"use client"

import Link from "next/link"
import { useRouter } from "next/navigation"
import { useState } from "react"
import { Database, Info, Upload } from "lucide-react"

import { FileDropzone, useNow } from "@/components/data"
import { DatasetStatus } from "@/components/dataset"
import { TextField } from "@/components/form"
import { LoadError, Loading, useCurrentMembership } from "@/components/org"
import { EmptyState, InfoTip, InlineError, Notice, Num, PageHeader, Spinner, VerdictChip } from "@/components/nz"
import { Button } from "@/components/ui/button"
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog"
import { api, messageFor, upload } from "@/lib/api"
import type { Dataset } from "@/lib/types"
import { formatDateTime, useApi } from "@/lib/use-api"

const ACCEPT = ".csv,.tsv,.txt,.xlsx,.xlsm,text/csv,application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"

type Sample = { label: string; rows: string; file: string; key: string; name: string }

const SAMPLE_GROUPS: { title: string; items: Sample[] }[] = [
  {
    title: "نظيفة (الأشيع)",
    items: [
      { label: "مواعيد عيادات (لتدريب نموذج)", rows: "1,000 صف", file: "clinic_appointments_clean.csv",
        key: "clinic_appointments_answer_key.csv", name: "مواعيد العيادات" },
      { label: "عملاء بنك", rows: "600 صف", file: "bank_accounts_clean.csv",
        key: "bank_accounts_answer_key.csv", name: "عملاء البنك" },
    ],
  },
  {
    title: "تحتاج تنظيف",
    items: [
      { label: "مرضى مستشفى", rows: "612 صفاً", file: "hospital_patients_test.csv", key: "hospital_patients_answer_key.csv",
        name: "مرضى المستشفى" },
      { label: "عملاء بنك", rows: "458 صفاً", file: "bank_customers_test.csv",
        key: "bank_customers_answer_key.csv", name: "عملاء البنك (غير منظّف)" },
      { label: "مطالبات تأمين (Excel)", rows: "780 صفاً", file: "insurance_claims_test.xlsx",
        key: "insurance_claims_answer_key.csv", name: "مطالبات التأمين" },
    ],
  },
]

type DemoTable = { name: string; rows: number }

function DbImport({ orgId }: { orgId: string }) {
  const router = useRouter()
  const [tables, setTables] = useState<DemoTable[] | null>(null)
  const [picked, setPicked] = useState<string[]>([])
  const [busy, setBusy] = useState<"connect" | "import" | null>(null)
  const [error, setError] = useState<string | null>(null)

  async function connect() {
    setBusy("connect")
    setError(null)
    try {
      const r = await api<{ available: boolean; tables: DemoTable[] }>(`/orgs/${orgId}/demo-db/tables`)
      if (!r.available) setError("قاعدة البيانات التجريبية غير مفعّلة في هذه النسخة.")
      else { setTables(r.tables); setPicked(r.tables.map((t) => t.name)) }
    } catch (e) {
      setError(messageFor(e))
    } finally {
      setBusy(null)
    }
  }

  async function importTables() {
    setBusy("import")
    setError(null)
    try {
      const ds = await api<Dataset>(`/orgs/${orgId}/demo-db/import`, { method: "POST", body: { tables: picked } })
      router.push(`/app/o/${orgId}/datasets/${ds.id}`)
    } catch (e) {
      setError(messageFor(e))
      setBusy(null)
    }
  }

  return (
    <div className="space-y-4">
      {!tables ? (
        <div className="space-y-2">
          <Button onClick={connect} disabled={busy !== null}>
            {busy === "connect" ? <Spinner className="size-4" /> : <Database data-icon="inline-start" />} اتصل بقاعدة البيانات التجريبية
          </Button>
          <p className="text-sm text-muted-foreground">في الاستخدام الفعلي يتصل نَظير بقواعد المنشأة من داخلها.</p>
        </div>
      ) : (
        <>
          <ul className="divide-y divide-border rounded-lg border border-border">
            {tables.map((t) => (
              <li key={t.name}>
                <label className="flex cursor-pointer items-center justify-between gap-3 px-4 py-2.5 text-sm">
                  <span className="flex items-center gap-3">
                    <input type="checkbox" className="size-4" checked={picked.includes(t.name)}
                      onChange={(e) => setPicked(e.target.checked ? [...picked, t.name] : picked.filter((x) => x !== t.name))} />
                    <bdi className="font-semibold">{t.name}</bdi>
                  </span>
                  <span className="text-muted-foreground"><Num>{t.rows.toLocaleString("en")}</Num> صف</span>
                </label>
              </li>
            ))}
          </ul>
          <Button onClick={importTables} disabled={!picked.length || busy !== null}>
            {busy === "import" ? <Spinner className="size-4" /> : <Upload data-icon="inline-start" />} استورد ومعالجة
          </Button>
        </>
      )}
      {error ? <InlineError>{error}</InlineError> : null}
    </div>
  )
}

function UploadDialog({ orgId, open, onOpenChange }: { orgId: string; open: boolean; onOpenChange: (v: boolean) => void }) {
  const router = useRouter()
  const [files, setFiles] = useState<File[]>([])
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)
  const [name, setName] = useState("")
  const [tab, setTab] = useState<"file" | "db">("file")
  const [loadingSample, setLoadingSample] = useState<string | null>(null)

  async function pickSample(sm: Sample) {
    setLoadingSample(sm.file)
    try {
      const res = await fetch(`/samples/${sm.file}`)
      if (!res.ok) throw new Error()
      const blob = await res.blob()
      setFiles([new File([blob], sm.file, { type: blob.type || "text/csv" })])
      setName(sm.name)
      setError(null)
    } catch {
      setError("تعذّر تحميل الملف التجريبي. جرّب مرة أخرى.")
    } finally {
      setLoadingSample(null)
    }
  }

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
      <DialogContent className="max-h-[92vh] overflow-y-auto sm:max-w-2xl">
        <DialogHeader>
          <DialogTitle className="text-lg">رفع بيانات</DialogTitle>
          <DialogDescription>CSV أو Excel · كل ورقة جدول.</DialogDescription>
        </DialogHeader>
        <div className="flex gap-1 rounded-lg bg-muted p-1" role="tablist" aria-label="المصدر">
          {([["file", "ملف"], ["db", "الاتصال بقاعدة بيانات"]] as const).map(([v, label]) => (
            <button key={v} type="button" role="tab" aria-selected={tab === v} onClick={() => setTab(v)}
              className={tab === v ? "h-8 flex-1 rounded-md bg-card px-3 text-sm font-semibold shadow-card" : "h-8 flex-1 rounded-md px-3 text-sm text-muted-foreground"}>
              {label}
            </button>
          ))}
        </div>
        {tab === "db" ? <DbImport orgId={orgId} /> : null}
        <form id="upload-form" hidden={tab !== "file"} onSubmit={onSubmit} className="space-y-5" noValidate>
          <Notice icon={Info}>نسخة عرض: استخدم بيانات تجريبية فقط.</Notice>
          <div className="space-y-3 rounded-lg border border-border bg-muted/40 px-4 py-3 text-sm">
            <p className="font-semibold">ملفات جاهزة</p>
            {SAMPLE_GROUPS.map((g) => (
              <div key={g.title}>
                <p className="mb-1 text-xs font-bold text-muted-foreground">{g.title}</p>
                <ul className="space-y-1.5">
                  {g.items.map((sm) => (
                    <li key={sm.file} className="flex flex-wrap items-center justify-between gap-2">
                      <span className="leading-6">
                        {sm.label} <span className="text-muted-foreground">· {sm.rows}</span>
                        <span className="block text-xs">
                          <a className="text-primary hover:underline" href={`/samples/${sm.file}`} download>الملف</a>
                          {" · "}<a className="text-primary hover:underline" href={`/samples/${sm.key}`} download>مفتاح الإجابة</a>
                        </span>
                      </span>
                      <Button type="button" size="sm" variant={files[0]?.name === sm.file ? "default" : "outline"}
                        onClick={() => pickSample(sm)} disabled={loadingSample !== null}>
                        {loadingSample === sm.file ? <Spinner className="size-3.5" /> : null}
                        {files[0]?.name === sm.file ? "تم اختياره" : "استخدم هذا الملف"}
                      </Button>
                    </li>
                  ))}
                </ul>
              </div>
            ))}
          </div>
          {error ? <InlineError>{error}</InlineError> : null}
          <TextField name="name" label="اسم مجموعة البيانات (اختياري)" placeholder="اختياري"
            value={name} onChange={(e) => setName(e.target.value)} />
          <FileDropzone files={files} onChange={setFiles} accept={ACCEPT} />
          <p className="flex items-center gap-1 text-xs text-muted-foreground">
            تُحذف الأصول بعد <Num>30</Num> دقيقة <InfoTip>تُحفظ الملفات الأصلية مشفّرة مدة جلسة المعالجة فقط، ثم تُحذف تلقائياً.</InfoTip>
          </p>
        </form>
        <DialogFooter className={tab === "file" ? undefined : "hidden"}>
          <Button variant="ghost" onClick={() => onOpenChange(false)}>إلغاء</Button>
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
