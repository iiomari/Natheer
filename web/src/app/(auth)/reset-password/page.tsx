"use client"

import Link from "next/link"
import { useSearchParams } from "next/navigation"
import { Suspense, useState } from "react"
import { CheckCircle2 } from "lucide-react"

import { AuthCard } from "@/components/auth-card"
import { PasswordField } from "@/components/form"
import { InlineError, Notice, Spinner } from "@/components/nz"
import { Button, buttonVariants } from "@/components/ui/button"
import { api, messageFor } from "@/lib/api"

function ResetForm() {
  const token = useSearchParams().get("token") ?? ""
  const [done, setDone] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)

  async function onSubmit(e: React.FormEvent<HTMLFormElement>) {
    e.preventDefault()
    const f = new FormData(e.currentTarget)
    const password = String(f.get("password") ?? "")
    if (password.length < 10) return setError("كلمة المرور يجب أن تكون 10 أحرف على الأقل.")
    if (password !== f.get("confirm")) return setError("كلمتا المرور غير متطابقتين.")
    setBusy(true)
    setError(null)
    try {
      await api("/auth/reset-password", { method: "POST", body: { token, password } })
      setDone(true)
    } catch (err) {
      setError(messageFor(err))
    } finally {
      setBusy(false)
    }
  }

  if (!token) {
    return (
      <AuthCard title="رابط غير مكتمل" description="افتح الرابط كما وصلك من مدير منشأتك، أو اطلب منه رابطاً جديداً.">
        <Link href="/login" className={buttonVariants({ size: "lg", variant: "outline", className: "w-full" })}>تسجيل الدخول</Link>
      </AuthCard>
    )
  }
  return (
    <AuthCard title="تعيين كلمة مرور جديدة" description="سيُسجَّل خروجك من كل الأجهزة بعد التغيير.">
      {done ? (
        <div className="space-y-5">
          <Notice tone="twin" icon={CheckCircle2}>تم تغيير كلمة المرور.</Notice>
          <Link href="/login" className={buttonVariants({ size: "lg", className: "w-full" })}>تسجيل الدخول</Link>
        </div>
      ) : (
        <form onSubmit={onSubmit} className="space-y-5" noValidate>
          {error ? <InlineError>{error}</InlineError> : null}
          <PasswordField name="password" label="كلمة المرور الجديدة" required autoComplete="new-password" hint="10 أحرف على الأقل." />
          <PasswordField name="confirm" label="تأكيد كلمة المرور" required autoComplete="new-password" />
          <Button type="submit" size="lg" className="w-full" disabled={busy}>
            {busy ? <Spinner className="size-4" /> : null}
            حفظ كلمة المرور
          </Button>
        </form>
      )}
    </AuthCard>
  )
}

export default function ResetPasswordPage() {
  return (
    <Suspense>
      <ResetForm />
    </Suspense>
  )
}
