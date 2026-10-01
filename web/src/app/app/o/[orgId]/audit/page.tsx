"use client"

import { ScrollText } from "lucide-react"

import { AdminOnly, LoadError, Loading, useCurrentMembership } from "@/components/org"
import { EmptyState, PageHeader } from "@/components/nz"
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table"
import type { AuditEvent, Member } from "@/lib/types"
import { formatDateTime, useApi } from "@/lib/use-api"

const ACTIONS: Record<string, string> = {
  "org.created": "إنشاء المنشأة",
  "org.updated": "تعديل بيانات المنشأة",
  "member.invited": "إرسال دعوة",
  "member.invitation_revoked": "إلغاء دعوة",
  "member.joined": "انضمام عضو",
  "member.role_changed": "تغيير دور عضو",
  "member.data_manager_changed": "تغيير صلاحية مدير البيانات",
  "member.removed": "إزالة عضو",
}

const ROLE: Record<string, string> = { admin: "مدير", member: "عضو" }

function details(e: AuditEvent): string {
  const m = e.meta ?? {}
  if (e.action === "member.role_changed") return `${ROLE[String(m.old)] ?? "—"} ← ${ROLE[String(m.new)] ?? "—"}`
  if (e.action === "member.data_manager_changed") return m.new ? "منح" : "سحب"
  if (e.action === "member.invited" || e.action === "member.joined") return ROLE[String(m.role)] ?? ""
  return ""
}

export default function AuditPage() {
  const { orgId, membership } = useCurrentMembership()
  const isAdmin = membership?.role === "admin"
  const events = useApi<AuditEvent[]>(isAdmin ? `/orgs/${orgId}/audit?n=200` : null)
  const members = useApi<Member[]>(isAdmin ? `/orgs/${orgId}/members` : null)
  if (!isAdmin) return <AdminOnly />
  const names = new Map(members.data?.map((m) => [m.user_id, m.full_name]))

  return (
    <>
      <PageHeader title="سجل التدقيق" description="من فعل ماذا ومتى. لا يحتوي السجل أي قيمة من البيانات." />
      {events.loading ? (
        <Loading />
      ) : events.error ? (
        <LoadError error={events.error} />
      ) : !events.data?.length ? (
        <EmptyState icon={ScrollText} title="لا أحداث بعد" />
      ) : (
        <div className="overflow-x-auto rounded-xl border border-border bg-card shadow-card">
          <Table>
            <TableHeader className="bg-muted/60">
              <TableRow>
                <TableHead className="h-11 px-5 text-start font-bold">الإجراء</TableHead>
                <TableHead className="h-11 px-5 text-start font-bold">التفاصيل</TableHead>
                <TableHead className="h-11 px-5 text-start font-bold">المنفّذ</TableHead>
                <TableHead className="h-11 px-5 text-start font-bold">الوقت</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {events.data.map((e) => (
                <TableRow key={e.id}>
                  <TableCell className="px-5 py-3.5 font-semibold">{ACTIONS[e.action] ?? e.action}</TableCell>
                  <TableCell className="px-5 py-3.5 text-muted-foreground">{details(e) || "—"}</TableCell>
                  <TableCell className="px-5 py-3.5">{(e.actor_user_id && names.get(e.actor_user_id)) || "عضو سابق"}</TableCell>
                  <TableCell className="px-5 py-3.5 text-muted-foreground">{formatDateTime(e.at)}</TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </div>
      )}
    </>
  )
}
