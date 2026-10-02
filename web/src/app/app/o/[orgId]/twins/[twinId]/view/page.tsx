"use client"

import Link from "next/link"
import { useParams } from "next/navigation"
import { ArrowRight, Download } from "lucide-react"

import { LoadError, Loading, useCurrentMembership } from "@/components/org"
import { PageHeader, VerdictChip } from "@/components/nz"
import { TwinTable } from "@/components/twin-table"
import { buttonVariants } from "@/components/ui/button"
import type { Twin } from "@/lib/types"
import { formatDateTime, useApi } from "@/lib/use-api"

export default function TwinViewPage() {
  const { twinId } = useParams<{ twinId: string }>()
  const { orgId } = useCurrentMembership()
  const twin = useApi<Twin>(`/orgs/${orgId}/twins/${twinId}`)
  const t = twin.data
  if (twin.loading) return <Loading />
  if (twin.error || !t) return <LoadError error={twin.error} />
  return (
    <>
      <Link href={`/app/o/${orgId}/twins/${t.id}`} className="mb-4 inline-flex items-center gap-1 text-sm font-semibold text-primary hover:underline">
        <ArrowRight className="size-4" /> تقرير النظير
      </Link>
      <PageHeader
        title={`النظير: ${t.dataset_name}`}
        description={<>وُلّد {formatDateTime(t.created_at)} · بيانات نظيرة لا تحتوي أي شخص حقيقي</>}
        actions={
          <>
            <VerdictChip verdict={t.verdict} />
            <a href={`/api/orgs/${orgId}/twins/${t.id}/download.xlsx`} className={buttonVariants()}>
              <Download data-icon="inline-start" /> تحميل Excel
            </a>
            <a href={`/api/orgs/${orgId}/twins/${t.id}/download.csv`} className={buttonVariants({ variant: "outline" })}>
              <Download data-icon="inline-start" /> تحميل CSV
            </a>
          </>
        }
      />
      {t.withheld || t.purged ? (
        <p className="text-muted-foreground">{t.purged ? "حُذف هذا النظير بعد انتهاء مدة الاحتفاظ." : "النظير محجوب لأنه لم يجتز فحص التسريب."}</p>
      ) : (
        <TwinTable endpoint={`/orgs/${orgId}/twins/${t.id}/rows`} />
      )}
    </>
  )
}
