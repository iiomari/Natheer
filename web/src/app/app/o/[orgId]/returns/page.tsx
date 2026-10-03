"use client"

import { useState } from "react"
import { Link2, Undo2 } from "lucide-react"

import { LoadError, Loading, useCurrentMembership } from "@/components/org"
import { Chip, EmptyState, Notice, PageHeader } from "@/components/nz"
import { RelinkDialog, VerificationReport } from "@/components/returns"
import { SafeBoundary } from "@/components/safe-boundary"
import { Button } from "@/components/ui/button"
import type { ReturnInfo } from "@/lib/types"
import { formatDateTime, useApi } from "@/lib/use-api"

const STATUS: Record<string, { label: string; tone: "neutral" | "primary" | "twin" | "sensitive" }> = {
  none: { label: "لم يُربط بعد", tone: "neutral" },
  running: { label: "جارٍ الربط", tone: "primary" },
  ready: { label: "جاهز للتنزيل", tone: "twin" },
  failed: { label: "تعذّر الربط", tone: "sensitive" },
  expired: { label: "حُذف الملف المربوط", tone: "neutral" },
}

export default function ReturnsPage() {
  const { orgId, membership } = useCurrentMembership()
  const list = useApi<ReturnInfo[]>(`/orgs/${orgId}/returns`)
  const [open, setOpen] = useState<string | null>(null)
  const isAdmin = membership?.role === "admin"

  return (
    <>
      <PageHeader title="المرتجعات" description="النتائج التي أعادها المستلمون، وتحقق نَظير من كل صف فيها برمز التحقق." />
      {list.loading && !list.data ? (
        <Loading />
      ) : list.error ? (
        <LoadError error={list.error} />
      ) : !list.data?.length ? (
        <EmptyState
          icon={Undo2}
          title="لا مرتجعات بعد"
          description="عندما يعيد مستلم نتائجه تظهر هنا مع تقرير التحقق، ويستطيع مدير المنشأة إعادة ربطها بالسجلات الحقيقية."
        />
      ) : (
        <div className="space-y-6">
          {!isAdmin ? <Notice>إعادة الربط بالسجلات الحقيقية متاحة لمدير المنشأة فقط.</Notice> : null}
          {list.data.map((r) => {
            const st = STATUS[r.relink?.status ?? "none"] ?? STATUS.none
            return (
              <SafeBoundary key={r.id}>
              <div className="space-y-5 rounded-xl border border-border bg-card p-6 shadow-card">
                <div className="flex flex-wrap items-start justify-between gap-3">
                  <div>
                    <p className="text-lg font-bold"><bdi>{r.file_name}</bdi></p>
                    <p className="text-sm text-muted-foreground">
                      {r.dataset_name} · من {r.recipient || "مستلم"} · {formatDateTime(r.created_at)}
                    </p>
                  </div>
                  <div className="flex items-center gap-2">
                    <Chip tone={st.tone}>{st.label}</Chip>
                    {isAdmin && r.relinkable && !r.legacy ? (
                      <Button onClick={() => setOpen(r.id)}>
                        <Link2 data-icon="inline-start" /> إعادة الربط
                      </Button>
                    ) : null}
                  </div>
                </div>
                <VerificationReport report={r.report} legacy={r.legacy} />
              </div>
              </SafeBoundary>
            )
          })}
        </div>
      )}
      <RelinkDialog orgId={orgId} returnId={open} open={open !== null} onOpenChange={(o) => !o && setOpen(null)}
        onChanged={() => void list.reload()} />
    </>
  )
}
