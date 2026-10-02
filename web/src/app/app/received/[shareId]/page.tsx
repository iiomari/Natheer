"use client"

import Link from "next/link"
import { useParams } from "next/navigation"
import { useState } from "react"
import { ArrowRight, Download, ShieldCheck } from "lucide-react"
import { toast } from "sonner"

import { CleaningNote } from "@/components/cleaning"
import { ReturnResults } from "@/components/returns"
import { DataTable } from "@/components/data"
import { LoadError, Loading } from "@/components/org"
import { Chip, EmptyState, Notice, Num, PageHeader, Section, Spinner, VerdictChip } from "@/components/nz"
import { Button } from "@/components/ui/button"
import { api, messageFor } from "@/lib/api"
import type { Received } from "@/lib/types"
import { formatDay, useApi } from "@/lib/use-api"

export default function ReceivedDetail() {
  const { shareId } = useParams<{ shareId: string }>()
  const r = useApi<Received>(`/received/${shareId}`)
  const [busy, setBusy] = useState<string | null>(null)
  if (r.loading) return <Loading />
  if (r.error || !r.data) return <LoadError error={r.error} />
  const d = r.data

  async function download(format: "csv" | "xlsx") {
    setBusy(format)
    try {
      const { url } = await api<{ url: string }>(`/received/${shareId}/download`, { method: "POST", body: { format } })
      window.location.assign(url)
    } catch (e) {
      toast.error(messageFor(e))
    } finally {
      setTimeout(() => setBusy(null), 1500)
    }
  }

  return (
    <>
      <Link href="/app/received" className="mb-4 inline-flex items-center gap-1 text-sm font-semibold text-primary hover:underline">
        <ArrowRight className="size-4" /> البيانات المستلمة
      </Link>
      <PageHeader
        title={d.dataset_name}
        description={<>من {d.org_name} · تنتهي {formatDay(d.expires_at)}</>}
        actions={
          d.status === "active" ? (
            <>
              {d.formats.includes("csv") ? (
                <Button onClick={() => download("csv")} disabled={busy !== null}>
                  {busy === "csv" ? <Spinner className="size-4" /> : <Download data-icon="inline-start" />} تحميل CSV
                </Button>
              ) : null}
              {d.formats.includes("xlsx") ? (
                <Button variant="outline" onClick={() => download("xlsx")} disabled={busy !== null}>
                  {busy === "xlsx" ? <Spinner className="size-4" /> : <Download data-icon="inline-start" />} تحميل Excel
                </Button>
              ) : null}
            </>
          ) : null
        }
      />
      <div className="mb-8">
        <Notice tone="twin" icon={ShieldCheck}>هذه بيانات نظيرة لا تحتوي أي شخص حقيقي.</Notice>
      </div>
      {d.status !== "active" ? (
        <EmptyState
          title={d.status === "expired" ? "انتهت صلاحية هذه المشاركة" : "ألغت المنشأة هذه المشاركة"}
          description="لم يعد التنزيل متاحاً. تواصل مع المنشأة إن احتجت البيانات مجدداً."
        />
      ) : (
        <div className="space-y-10">
          <div className="flex flex-wrap items-center gap-3">
            <VerdictChip verdict={d.verdict} />
            <Chip tone="primary">{d.mode === "masked" ? "نظير مقنّع" : "نظير اصطناعي"}</Chip>
            {d.proof?.leak ? (
              <span className="text-sm text-muted-foreground">
                فحص التسريب: <Num>{d.proof.leak.leaks}</Num> معرّف حقيقي في <Num>{d.proof.leak.cells.toLocaleString("en")}</Num> خلية
              </span>
            ) : null}
          </div>
          {d.message ? <Notice>{d.message}</Notice> : null}
          {d.preview?.map((t) => (
            <Section key={t.table} title={t.table} description={<>أول <Num>{t.rows.length}</Num> صفاً للمعاينة</>}>
              <DataTable columns={t.columns} rows={t.rows} />
            </Section>
          ))}
          <CleaningNote cleaning={d.cleaning} />
          <ReturnResults share={d} />
        </div>
      )}
    </>
  )
}
