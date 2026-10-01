import { Share2 } from "lucide-react"

import { EmptyState, PageHeader } from "@/components/nz"

export default function SharesPage() {
  return (
    <>
      <PageHeader title="المشاركات" description="النظائر التي شاركتها منشأتك، وحالتها ومرات تنزيلها." />
      <EmptyState
        icon={Share2}
        title="لا مشاركات بعد"
        description="بعد توليد نظير ناجح ستشاركه من هنا مع أعضاء منشأتك أو جهات خارجية، بتاريخ انتهاء وصيغ محددة."
      />
    </>
  )
}
