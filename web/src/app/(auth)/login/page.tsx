"use client"

import Link from "next/link"
import { useRouter, useSearchParams } from "next/navigation"
import { Suspense, useState } from "react"

import { AuthCard } from "@/components/auth-card"
import { EmailField, PasswordField } from "@/components/form"
import { InlineError, Spinner } from "@/components/nz"
import { Button } from "@/components/ui/button"
import { api, messageFor } from "@/lib/api"
import { safeNext } from "@/lib/nav"

function LoginForm() {
  const router = useRouter()
  const params = useSearchParams()
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)

  async function onSubmit(e: React.FormEvent<HTMLFormElement>) {
    e.preventDefault()
    const form = new FormData(e.currentTarget)
    setBusy(true)
    setError(null)
    try {
      await api("/auth/login", { method: "POST", body: { email: form.get("email"), password: form.get("password") } })
      router.replace(safeNext(params.get("next")))
    } catch (err) {
      setError(messageFor(err))
      setBusy(false)
    }
  }

  return (
    <AuthCard
      title="تسجيل الدخول"
      description="ادخل إلى مساحة منشأتك أو إلى البيانات المشاركة معك."
      footer={
        <>
          ليس لديك حساب؟{" "}
          <Link href="/signup" className="font-semibold text-primary hover:underline">
            أنشئ حساباً
          </Link>
        </>
      }
    >
      <form onSubmit={onSubmit} className="space-y-5" noValidate>
        {error ? <InlineError>{error}</InlineError> : null}
        <EmailField name="email" required autoFocus />
        <PasswordField name="password" required autoComplete="current-password" />
        <div className="flex justify-end">
          <Link href="/forgot-password" className="text-sm font-semibold text-primary hover:underline">
            نسيت كلمة المرور؟
          </Link>
        </div>
        <Button type="submit" size="lg" className="w-full" disabled={busy}>
          {busy ? <Spinner className="size-4" /> : null}
          دخول
        </Button>
      </form>
    </AuthCard>
  )
}

export default function LoginPage() {
  return (
    <Suspense>
      <LoginForm />
    </Suspense>
  )
}
