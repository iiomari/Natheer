"use client"

import Link from "next/link"

import { Button } from "@/components/ui/button"

export default function AppError({ reset }: { error: Error; reset: () => void }) {
  return (
    <div className="mx-auto max-w-md py-16 text-center">
      <h1 className="text-2xl font-bold">تعذّر تحميل هذه الصفحة</h1>
      <p className="mt-2 text-muted-foreground">حدث خطأ غير متوقع. جرّب مرة أخرى.</p>
      <div className="mt-6 flex justify-center gap-3">
        <Button onClick={reset}>أعد المحاولة</Button>
        <Link href="/app" className="inline-flex h-10 items-center px-4 text-sm font-semibold text-primary">الرئيسية</Link>
      </div>
    </div>
  )
}
