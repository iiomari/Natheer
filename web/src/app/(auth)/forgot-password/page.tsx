"use client"

import Link from "next/link"
import { useState } from "react"
import { MailCheck } from "lucide-react"

import { AuthCard } from "@/components/auth-card"
import { EmailField } from "@/components/form"
import { InlineError, Notice, Spinner } from "@/components/nz"
import { Button } from "@/components/ui/button"
import { api, messageFor } from "@/lib/api"

export default function ForgotPasswordPage() {
  const [sent, setSent] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)

  async function onSubmit(e: React.FormEvent<HTMLFormElement>) {
    e.preventDefault()
    setBusy(true)
    setError(null)
    try {
      await api("/auth/forgot-password", { method: "POST", body: { email: new FormData(e.currentTarget).get("email") } })
      setSent(true)
    } catch (err) {
      setError(messageFor(err))
    } finally {
      setBusy(false)
    }
  }

  return (
    <AuthCard
      title="استعادة كلمة المرور"
      description="أدخل بريدك، وسنرسل رابطاً لتعيين كلمة مرور جديدة."
      footer={<Link href="/login" className="font-semibold text-primary hover:underline">العودة لتسجيل الدخول</Link>}
    >
      {sent ? (
        <Notice tone="twin" icon={MailCheck}>
          إن كان هذا البريد مسجّلاً فستصلك رسالة خلال دقائق. الرابط صالح لساعة واحدة.
        </Notice>
      ) : (
        <form onSubmit={onSubmit} className="space-y-5" noValidate>
          {error ? <InlineError>{error}</InlineError> : null}
          <EmailField name="email" required autoFocus />
          <Button type="submit" size="lg" className="w-full" disabled={busy}>
            {busy ? <Spinner className="size-4" /> : null}
            إرسال الرابط
          </Button>
        </form>
      )}
    </AuthCard>
  )
}
