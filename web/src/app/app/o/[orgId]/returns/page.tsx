"use client"

import { useState } from "react"
import { Link2, Undo2 } from "lucide-react"

import { LoadError, Loading, useCurrentMembership } from "@/components/org"
import { Chip, EmptyState, Notice, Num, PageHeader } from "@/components/nz"
import { RejectedCounts, RelinkDialog } from "@/components/returns"
import { Button } from "@/components/ui/button"
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table"
import type { ReturnInfo } from "@/lib/types"
import { formatDateTime, useApi } from "@/lib/use-api"

const STATUS: Record<string, { label: string; tone: "neutral" | "primary" | "twin" | "sensitive" }> = {
  none: { label: "لم يُربط", tone: "neutral" },
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
      <PageHeader title="المرتجعات" description="النتائج التي أعادها المستلمون بعد العمل على النظير، بعد التحقق منها." />
      {list.loading && !list.data ? (
        <Loading />
      ) : list.error ? (
        <LoadError error={list.error} />
      ) : !list.data?.length ? (
        <EmptyState
          icon={Undo2}
          title="لا مرتجعات بعد"
          description="عندما يعيد مستلم نتائجه تظهر هنا مع نتيجة التحقق، ويستطيع مدير المنشأة إعادة ربطها بالسجلات الحقيقية."
        />
      ) : (
        <div className="space-y-4">
          {!isAdmin ? <Notice>إعادة الربط بالسجلات الحقيقية متاحة لمدير المنشأة فقط.</Notice> : null}
          <div className="overflow-x-auto rounded-xl border border-border bg-card shadow-card">
            <Table>
              <TableHeader className="bg-muted/60">
                <TableRow>
                  <TableHead className="px-5 text-start font-bold">الملف</TableHead>
                  <TableHead className="px-5 text-start font-bold">المستلم</TableHead>
                  <TableHead className="px-5 text-start font-bold">الصفوف المقبولة</TableHead>
                  <TableHead className="px-5 text-start font-bold">المرفوض</TableHead>
                  <TableHead className="px-5 text-start font-bold">إعادة الربط</TableHead>
                  <TableHead className="px-5" />
                </TableRow>
              </TableHeader>
              <TableBody>
                {list.data.map((r) => {
                  const st = STATUS[r.relink?.status ?? "none"]
                  return (
                    <TableRow key={r.id}>
                      <TableCell className="px-5 py-3">
                        <bdi className="font-semibold">{r.file_name}</bdi>
                        <span className="block text-xs text-muted-foreground">
                          {r.dataset_name} · {formatDateTime(r.created_at)}
                        </span>
                      </TableCell>
                      <TableCell className="px-5 py-3">{r.recipient}</TableCell>
                      <TableCell className="px-5 py-3">
                        <Num>{r.rows_accepted.toLocaleString("en")}</Num> من <Num>{r.rows_total.toLocaleString("en")}</Num>
                      </TableCell>
                      <TableCell className="px-5 py-3 text-sm"><RejectedCounts rejected={r.rejected} /></TableCell>
                      <TableCell className="px-5 py-3"><Chip tone={st.tone}>{st.label}</Chip></TableCell>
                      <TableCell className="px-5 py-3 text-end">
                        {isAdmin && r.available ? (
                          <Button size="sm" variant="outline" onClick={() => setOpen(r.id)}>
                            <Link2 data-icon="inline-start" /> إعادة الربط
                          </Button>
                        ) : null}
                      </TableCell>
                    </TableRow>
                  )
                })}
              </TableBody>
            </Table>
          </div>
        </div>
      )}
      <RelinkDialog orgId={orgId} returnId={open} open={open !== null} onOpenChange={(o) => !o && setOpen(null)}
        onChanged={() => void list.reload()} />
    </>
  )
}
