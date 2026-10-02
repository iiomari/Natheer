"use client"

import { Share2 } from "lucide-react"
import { toast } from "sonner"

import { LoadError, Loading, useCurrentMembership } from "@/components/org"
import { Chip, EmptyState, Num, PageHeader } from "@/components/nz"
import { Button } from "@/components/ui/button"
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table"
import { api, messageFor } from "@/lib/api"
import type { ShareInfo } from "@/lib/types"
import { formatDay, useApi } from "@/lib/use-api"

const SHARE_STATUS = {
  active: { label: "نشطة", tone: "twin" },
  expired: { label: "منتهية", tone: "neutral" },
  revoked: { label: "ملغاة", tone: "sensitive" },
} as const

export default function SharesPage() {
  const { orgId, membership } = useCurrentMembership()
  const canManage = membership?.role === "admin" || membership?.data_manager
  const list = useApi<ShareInfo[]>(canManage ? `/orgs/${orgId}/shares` : null)

  async function revoke(id: string) {
    try {
      await api(`/orgs/${orgId}/shares/${id}/revoke`, { method: "POST" })
      toast.success("أُلغيت المشاركة. لم يعد بإمكان المستلمين التنزيل.")
      await list.reload()
    } catch (e) {
      toast.error(messageFor(e))
    }
  }

  return (
    <>
      <PageHeader title="المشاركات" description="النظائر التي شاركتها منشأتك، وحالتها ومرات تنزيلها." />
      {!canManage ? (
        <EmptyState icon={Share2} title="هذه الصفحة للمدير ومدير البيانات" />
      ) : list.loading ? (
        <Loading />
      ) : list.error ? (
        <LoadError error={list.error} />
      ) : !list.data?.length ? (
        <EmptyState icon={Share2} title="لا مشاركات بعد" description="بعد توليد نظير ناجح، شاركه من صفحة تقريره." />
      ) : (
        <div className="overflow-x-auto rounded-xl border border-border bg-card shadow-card">
          <Table>
            <TableHeader className="bg-muted/60">
              <TableRow>
                <TableHead className="px-5 text-start font-bold">البيانات</TableHead>
                <TableHead className="px-5 text-start font-bold">الحالة</TableHead>
                <TableHead className="px-5 text-start font-bold">المستلمون</TableHead>
                <TableHead className="px-5 text-start font-bold">الروابط</TableHead>
                <TableHead className="px-5 text-start font-bold">التنزيلات</TableHead>
                <TableHead className="px-5 text-start font-bold">تنتهي</TableHead>
                <TableHead className="px-5"><span className="sr-only">إجراءات</span></TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {list.data.map((s) => {
                const st = SHARE_STATUS[s.status]
                const accepted = s.links.filter((l) => l.accepted).length
                return (
                  <TableRow key={s.id}>
                    <TableCell className="px-5 py-3.5 font-semibold">
                      {s.dataset_name}
                      <span className="ms-2 text-xs text-muted-foreground">{s.mode === "masked" ? "مقنّع" : "اصطناعي"}</span>
                    </TableCell>
                    <TableCell className="px-5 py-3.5"><Chip tone={st.tone}>{st.label}</Chip></TableCell>
                    <TableCell className="px-5 py-3.5"><Num>{s.recipients}</Num></TableCell>
                    <TableCell className="px-5 py-3.5 text-sm text-muted-foreground">
                      {s.links.length ? <><Num>{accepted}</Num> من <Num>{s.links.length}</Num> قُبلت</> : "—"}
                    </TableCell>
                    <TableCell className="px-5 py-3.5"><Num>{s.download_count}</Num></TableCell>
                    <TableCell className="px-5 py-3.5 text-muted-foreground">{formatDay(s.expires_at)}</TableCell>
                    <TableCell className="px-5 py-3.5">
                      {s.status === "active" ? <Button size="sm" variant="outline" onClick={() => revoke(s.id)}>إلغاء</Button> : null}
                    </TableCell>
                  </TableRow>
                )
              })}
            </TableBody>
          </Table>
        </div>
      )}
    </>
  )
}
