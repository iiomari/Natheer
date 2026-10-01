"use client"

import Link from "next/link"
import { useSearchParams } from "next/navigation"
import { Suspense, useEffect, useRef, useState } from "react"
import { CheckCircle2 } from "lucide-react"

import { AuthCard } from "@/components/auth-card"
import { InlineError, Notice, Spinner } from "@/components/nz"
import { buttonVariants } from "@/components/ui/button"
import { api, messageFor } from "@/lib/api"

function Verify() {
  const token = useSearchParams().get("token") ?? ""
  const [state, setState] = useState<"working" | "done" | "error">(token ? "working" : "error")
  const [error, setError] = useState<string>("الرابط غير مكتمل. افتحه كما وصلك في البريد.")
  const started = useRef(false)

  useEffect(() => {
    if (!token || started.current) return
    started.current = true
    api("/auth/verify-email", { method: "POST", body: { token } })
      .then(() => setState("done"))
      .catch((err) => {
        setError(messageFor(err))
        setState("error")
      })
  }, [token])

  return (
    <AuthCard title="تأكيد البريد الإلكتروني">
      {state === "working" ? (
        <div className="flex items-center gap-3 text-muted-foreground">
          <Spinner className="size-4" /> نتحقق من الرابط…
        </div>
      ) : state === "done" ? (
        <div className="space-y-5">
          <Notice tone="twin" icon={CheckCircle2}>تم تأكيد بريدك. يمكنك الآن استلام البيانات المشاركة معك.</Notice>
          <Link href="/app" className={buttonVariants({ size: "lg", className: "w-full" })}>الذهاب إلى مساحتي</Link>
        </div>
      ) : (
        <div className="space-y-5">
          <InlineError>{error}</InlineError>
          <Link href="/app" className={buttonVariants({ size: "lg", variant: "outline", className: "w-full" })}>
            طلب رابط جديد من مساحتي
          </Link>
        </div>
      )}
    </AuthCard>
  )
}

export default function VerifyEmailPage() {
  return (
    <Suspense>
      <Verify />
    </Suspense>
  )
}
