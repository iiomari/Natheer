"use client"

import Link from "next/link"
import { Inbox } from "lucide-react"

import { LoadError, Loading } from "@/components/org"
import { Chip, EmptyState, Num, PageHeader, VerdictChip } from "@/components/nz"
import type { Received } from "@/lib/types"
import { formatDay, useApi } from "@/lib/use-api"

const STATUS = {
  active: { label: "متاحة", tone: "twin" },
  expired: { label: "منتهية", tone: "neutral" },
  revoked: { label: "ملغاة", tone: "sensitive" },
} as const

export default function ReceivedPage() {
  const list = useApi<Received[]>("/received")
  return (
    <>
      <PageHeader title="البيانات المستلمة" description="النظائر التي شاركتها معك المنشآت. هذه بيانات نظيرة لا تحتوي أي شخص حقيقي." />
      {list.loading ? (
        <Loading />
      ) : list.error ? (
        <LoadError error={list.error} />
      ) : !list.data?.length ? (
        <EmptyState
          icon={Inbox}
          title="لم تصلك بيانات بعد"
          description="عندما تشاركك منشأة نظيراً يظهر هنا. إن وصلك رابط مشاركة فافتحه وأنت مسجّل الدخول."
        />
      ) : (
        <ul className="grid gap-4">
          {list.data.map((r) => (
            <li key={r.id}>
              <Link
                href={`/app/received/${r.id}`}
                className="flex flex-wrap items-center justify-between gap-4 rounded-xl border border-border bg-card p-5 shadow-card transition-colors hover:border-primary/40"
              >
                <div className="min-w-0">
                  <p className="truncate text-lg font-bold">{r.dataset_name}</p>
                  <p className="mt-1 text-sm text-muted-foreground">
                    من {r.org_name} · <Num>{r.tables.reduce((a, t) => a + t.rows, 0).toLocaleString("en")}</Num> صف · تنتهي {formatDay(r.expires_at)}
                  </p>
                </div>
                <div className="flex items-center gap-2">
                  <VerdictChip verdict={r.verdict} />
                  <Chip tone={STATUS[r.status].tone}>{STATUS[r.status].label}</Chip>
                </div>
              </Link>
            </li>
          ))}
        </ul>
      )}
    </>
  )
}
