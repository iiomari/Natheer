"use client"

import { Inbox, MailWarning } from "lucide-react"

import { EmptyState, Notice, PageHeader } from "@/components/nz"
import { useSession } from "@/lib/session"

export default function ReceivedPage() {
  const { me } = useSession()
  return (
    <>
      <PageHeader title="البيانات المستلمة" description="النظائر التي شاركتها معك المنشآت. هذه بيانات نظيرة لا تحتوي أي شخص حقيقي." />
      {me && !me.email_verified ? (
        <div className="mb-6">
          <Notice tone="review" icon={MailWarning}>
            أكّد بريدك الإلكتروني أولاً. لا تظهر البيانات المشاركة لحساب غير مؤكَّد.
          </Notice>
        </div>
      ) : null}
      <EmptyState icon={Inbox} title="لم تصلك بيانات بعد" description="عندما تشارك منشأة نظيراً مع بريدك يظهر هنا مع تاريخ انتهائه ونتيجة فحصه." />
    </>
  )
}
