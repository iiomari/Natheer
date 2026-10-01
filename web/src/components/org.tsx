"use client"

import { useParams } from "next/navigation"
import { Lock } from "lucide-react"

import { EmptyState, Spinner } from "@/components/nz"
import { messageFor } from "@/lib/api"
import { useSession } from "@/lib/session"
import type { MembershipRef } from "@/lib/types"

/** The caller's membership in the organization in the URL (from /me; the API re-checks every request). */
export function useCurrentMembership(): { orgId: string; membership: MembershipRef | undefined } {
  const { orgId } = useParams<{ orgId: string }>()
  const { me } = useSession()
  return { orgId, membership: me?.memberships.find((m) => m.org_id === orgId) }
}

export function Loading() {
  return (
    <div className="flex items-center gap-3 py-16 text-muted-foreground">
      <Spinner className="size-4" /> جارٍ التحميل…
    </div>
  )
}

export function LoadError({ error }: { error: unknown }) {
  return <EmptyState icon={Lock} title="تعذّر عرض هذه الصفحة" description={messageFor(error)} />
}

export function AdminOnly() {
  return <EmptyState icon={Lock} title="هذه الصفحة لمدير المنشأة" description="اطلب من مدير منشأتك منحك الصلاحية إن كنت تحتاجها." />
}
