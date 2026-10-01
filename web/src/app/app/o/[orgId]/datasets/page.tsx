import { Database, Info, Upload } from "lucide-react"

import { EmptyState, Notice, PageHeader } from "@/components/nz"
import { Button } from "@/components/ui/button"

export default function DatasetsPage() {
  return (
    <>
      <PageHeader
        title="مجموعات البيانات"
        description="ارفع جداولك لاكتشاف البيانات الشخصية وتوليد النظير."
        actions={
          <Button disabled>
            <Upload data-icon="inline-start" />
            رفع بيانات
          </Button>
        }
      />
      <div className="mb-6">
        <Notice icon={Info}>يُرجى استخدام بيانات تجريبية في هذه النسخة.</Notice>
      </div>
      <EmptyState
        icon={Database}
        title="لا توجد مجموعات بيانات بعد"
        description="رفع ملفات CSV وExcel والاتصال بقاعدة MySQL يُفعَّل في الإصدار القادم من المنصّة."
      />
    </>
  )
}
