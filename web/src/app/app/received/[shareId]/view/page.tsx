"use client"

import Link from "next/link"
import { useParams } from "next/navigation"
import { useState } from "react"
import { ArrowRight, Download } from "lucide-react"
import { toast } from "sonner"

import { LoadError, Loading } from "@/components/org"
import { PageHeader, Spinner } from "@/components/nz"
import { TwinTable } from "@/components/twin-table"
import { Button } from "@/components/ui/button"
import { api, messageFor } from "@/lib/api"
import type { Received } from "@/lib/types"
import { formatDay, useApi } from "@/lib/use-api"

export default function ReceivedViewPage() {
  const { shareId } = useParams<{ shareId: string }>()
  const share = useApi<Received>(`/received/${shareId}`)
  const [busy, setBusy] = useState<string | null>(null)
  const d = share.data
  if (share.loading) return <Loading />
  if (share.error || !d) return <LoadError error={share.error} />

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
      <Link href={`/app/received/${shareId}`} className="mb-4 inline-flex items-center gap-1 text-sm font-semibold text-primary hover:underline">
        <ArrowRight className="size-4" /> تفاصيل المشاركة
      </Link>
      <PageHeader
        title={d.dataset_name}
        description={<>من {d.org_name} · تنتهي {formatDay(d.expires_at)}</>}
        actions={
          d.status === "active" ? (
            <>
              {d.formats.includes("xlsx") ? (
                <Button onClick={() => download("xlsx")} disabled={busy !== null}>
                  {busy === "xlsx" ? <Spinner className="size-4" /> : <Download data-icon="inline-start" />} تحميل Excel
                </Button>
              ) : null}
              {d.formats.includes("csv") ? (
                <Button variant="outline" onClick={() => download("csv")} disabled={busy !== null}>
                  {busy === "csv" ? <Spinner className="size-4" /> : <Download data-icon="inline-start" />} تحميل CSV
                </Button>
              ) : null}
            </>
          ) : null
        }
      />
      {d.status === "active" ? <TwinTable endpoint={`/received/${shareId}/rows`} /> : <p className="text-muted-foreground">لم تعد هذه المشاركة متاحة.</p>}
    </>
  )
}
