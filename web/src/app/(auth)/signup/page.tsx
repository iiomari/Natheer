"use client"

import Link from "next/link"
import { useRouter, useSearchParams } from "next/navigation"
import { Suspense, useState } from "react"
import { Building2, UserRound } from "lucide-react"

import { AuthCard } from "@/components/auth-card"
import { EmailField, PasswordField, TextField } from "@/components/form"
import { InlineError, Spinner } from "@/components/nz"
import { Button } from "@/components/ui/button"
import { ApiError, api, messageFor } from "@/lib/api"
import { safeNext } from "@/lib/nav"
import { cn } from "@/lib/utils"

type Kind = "organization" | "individual"

const KINDS: { value: Kind; title: string; text: string; icon: typeof Building2 }[] = [
  { value: "organization", title: "منشأة", text: "ترفع البيانات وتولّد النظير وتشاركه.", icon: Building2 },
  { value: "individual", title: "فرد", text: "تستلم بيانات نظيرة وتعيد نتائجك.", icon: UserRound },
]

function SignupForm() {
  const router = useRouter()
  const next = useSearchParams().get("next")
  const [kind, setKind] = useState<Kind>(next ? "individual" : "organization")
  const [error, setError] = useState<string | null>(null)
  const [fieldErrors, setFieldErrors] = useState<Record<string, string>>({})
  const [busy, setBusy] = useState(false)

  async function onSubmit(e: React.FormEvent<HTMLFormElement>) {
    e.preventDefault()
    const f = new FormData(e.currentTarget)
    const password = String(f.get("password") ?? "")
    const errs: Record<string, string> = {}
    if (password.length < 10) errs.password = "10 أحرف على الأقل."
    if (!f.get("terms")) errs.terms = "يلزم الموافقة على الشروط."
    setFieldErrors(errs)
    if (Object.keys(errs).length) return
    setBusy(true)
    setError(null)
    try {
      await api("/auth/signup", {
        method: "POST",
        body: {
          account_type: kind,
          full_name: f.get("full_name"),
          org_name: kind === "organization" ? f.get("org_name") : undefined,
          email: f.get("email"),
          password,
        },
      })
      router.replace(next ? safeNext(next) : "/app?welcome=1")
    } catch (err) {
      if (err instanceof ApiError && err.code === "invalid_request") {
        setFieldErrors(Object.fromEntries(err.fields.map((k) => [k, "تحقّق من هذا الحقل."])))
      }
      setError(messageFor(err))
      setBusy(false)
    }
  }

  return (
    <AuthCard
      title="إنشاء حساب"
      description="اختر نوع الحساب. يمكن للمنشأة لاحقاً دعوة موظفيها."
      footer={
        <>
          لديك حساب؟{" "}
          <Link href={next ? `/login?next=${encodeURIComponent(next)}` : "/login"} className="font-semibold text-primary hover:underline">
            سجّل الدخول
          </Link>
        </>
      }
    >
      <form onSubmit={onSubmit} className="space-y-5" noValidate>
        <fieldset>
          <legend className="sr-only">نوع الحساب</legend>
          <div className="grid grid-cols-2 gap-3">
            {KINDS.map((k) => (
              <label
                key={k.value}
                className={cn(
                  "flex cursor-pointer flex-col gap-2 rounded-xl border p-4 transition-colors",
                  kind === k.value ? "border-primary bg-accent ring-2 ring-primary/20" : "border-border hover:bg-muted",
                )}
              >
                <input
                  type="radio"
                  name="kind"
                  value={k.value}
                  checked={kind === k.value}
                  onChange={() => setKind(k.value)}
                  className="sr-only"
                />
                <span className="flex items-center gap-2 font-bold">
                  <k.icon className="size-4.5 text-primary" aria-hidden="true" />
                  {k.title}
                </span>
                <span className="text-sm leading-6 text-muted-foreground">{k.text}</span>
              </label>
            ))}
          </div>
        </fieldset>
        {error ? <InlineError>{error}</InlineError> : null}
        <TextField name="full_name" label="الاسم الكامل" required autoComplete="name" error={fieldErrors.full_name} />
        {kind === "organization" ? (
          <TextField name="org_name" label="اسم المنشأة" required autoComplete="organization" error={fieldErrors.org_name} />
        ) : null}
        <EmailField name="email" required error={fieldErrors.email} />
        <PasswordField name="password" required autoComplete="new-password" hint="10 أحرف على الأقل." error={fieldErrors.password} />
        <div className="space-y-1">
          <label className="flex items-start gap-2.5 text-sm leading-6">
            <input type="checkbox" name="terms" className="mt-1 size-4 accent-[var(--primary)]" />
            <span>
              أوافق على{" "}
              <Link href="/terms" target="_blank" className="font-semibold text-primary hover:underline">الشروط</Link>{" "}
              و<Link href="/privacy" target="_blank" className="font-semibold text-primary hover:underline">سياسة الخصوصية</Link>.
            </span>
          </label>
          {fieldErrors.terms ? <p className="text-sm text-sensitive">{fieldErrors.terms}</p> : null}
        </div>
        <Button type="submit" size="lg" className="w-full" disabled={busy}>
          {busy ? <Spinner className="size-4" /> : null}
          إنشاء الحساب
        </Button>
      </form>
    </AuthCard>
  )
}

export default function SignupPage() {
  return (
    <Suspense>
      <SignupForm />
    </Suspense>
  )
}
