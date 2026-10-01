import { Undo2 } from "lucide-react"

import { EmptyState, PageHeader } from "@/components/nz"

export default function ReturnsPage() {
  return (
    <>
      <PageHeader title="المرتجعات" description="الملفات التي أعادها المستلمون بعد العمل على النظير." />
      <EmptyState
        icon={Undo2}
        title="لا مرتجعات بعد"
        description="عندما يعيد مستلم نتائجه تظهر هنا مع نتيجة التحقق، ويستطيع مدير المنشأة إعادة ربطها بالسجلات الحقيقية."
      />
    </>
  )
}
