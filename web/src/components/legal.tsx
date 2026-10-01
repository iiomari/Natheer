import { Chip } from "@/components/nz"

export function LegalPage({ title, updated, children }: { title: string; updated: string; children: React.ReactNode }) {
  return (
    <div className="mx-auto max-w-3xl px-4 py-16 sm:px-6">
      <Chip tone="review">مسودة قابلة للتعديل قبل الإطلاق التجاري</Chip>
      <h1 className="page-title mt-4">{title}</h1>
      <p className="mt-2 text-sm text-muted-foreground">آخر تحديث: {updated}</p>
      <div className="mt-10 space-y-8 text-[0.9375rem] leading-8 [&_h2]:section-title [&_h2]:mb-2 [&_li]:ms-5 [&_li]:list-disc">
        {children}
      </div>
    </div>
  )
}
