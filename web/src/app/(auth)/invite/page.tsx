"use client"

import Link from "next/link"
import { useRouter, useSearchParams } from "next/navigation"
import { Suspense, useEffect, useRef, useState } from "react"
import { Building2 } from "lucide-react"

import { AuthCard } from "@/components/auth-card"
import { PasswordField, TextField } from "@/components/form"
import { InlineError, Ltr, Spinner } from "@/components/nz"
import { Button, buttonVariants } from "@/components/ui/button"
import { ApiError, api, messageFor } from "@/lib/api"
import type { Me } from "@/lib/types"

type Preview = { org_name: string; email: string; role: "admin" | "member"; has_account: boolean }

function Invite() {
  const router = useRouter()
  const token = useSearchParams().get("token") ?? ""
  const [preview, setPreview] = useState<Preview | null>(null)
  const [me, setMe] = useState<Me | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(token ? null : "الرابط غير مكتمل. افتحه كما وصلك من المنشأة.")
  const [busy, setBusy] = useState(false)
  const started = useRef(false)

  useEffect(() => {
    if (!token || started.current) return
    started.current = true
    Promise.all([
      api<Preview>("/invitations/preview", { method: "POST", body: { token } }),
      api<Me>("/auth/me").catch((e) => (e instanceof ApiError && e.status === 401 ? null : Promise.reject(e))),
    ])
      .then(([p, m]) => {
        setPreview(p)
        setMe(m)
      })
      .catch((e) => setError(messageFor(e)))
      .finally(() => setLoading(false))
  }, [token])

  async function accept(body: Record<string, unknown> = {}) {
    setBusy(true)
    setError(null)
    try {
      await api("/invitations/accept", { method: "POST", body: { token, ...body } })
      router.replace("/app")
    } catch (e) {
      setError(messageFor(e))
      setBusy(false)
    }
  }

  if (loading && token) {
    return (
      <AuthCard title="دعوة للانضمام">
        <div className="flex items-center gap-3 text-muted-foreground"><Spinner className="size-4" /> نتحقق من الدعوة…</div>
      </AuthCard>
    )
  }
  if (!preview) {
    return (
      <AuthCard title="دعوة للانضمام">
        <InlineError>{error ?? "الرابط غير صالح."}</InlineError>
      </AuthCard>
    )
  }

  const signedInAsInvitee = me && me.email === preview.email
  const roleLabel = preview.role === "admin" ? "مدير" : "عضو"
  return (
    <AuthCard
      title={`الانضمام إلى ${preview.org_name}`}
      description={
        <>
          دعوة بصفة <strong>{roleLabel}</strong> للبريد <Ltr>{preview.email}</Ltr>.
        </>
      }
    >
      <div className="space-y-5">
        {error ? <InlineError>{error}</InlineError> : null}
        {me && !signedInAsInvitee ? (
          <>
            <InlineError>
              أنت مسجّل الدخول ببريد آخر (<Ltr>{me.email}</Ltr>). سجّل الخروج ثم افتح الرابط مجدداً.
            </InlineError>
            <Button
              size="lg"
              variant="outline"
              className="w-full"
              onClick={async () => {
                await api("/auth/logout", { method: "POST" }).catch(() => undefined)
                window.location.reload()
              }}
            >
              تسجيل الخروج
            </Button>
          </>
        ) : signedInAsInvitee ? (
          <Button size="lg" className="w-full" disabled={busy} onClick={() => accept()}>
            {busy ? <Spinner className="size-4" /> : <Building2 data-icon="inline-start" />}
            قبول الدعوة
          </Button>
        ) : preview.has_account ? (
          <Link
            href={`/login?next=${encodeURIComponent(`/invite?token=${token}`)}`}
            className={buttonVariants({ size: "lg", className: "w-full" })}
          >
            لديك حساب: سجّل الدخول للقبول
          </Link>
        ) : (
          <form
            className="space-y-5"
            noValidate
            onSubmit={(e) => {
              e.preventDefault()
              const f = new FormData(e.currentTarget)
              const password = String(f.get("password") ?? "")
              if (password.length < 10) return setError("كلمة المرور يجب أن تكون 10 أحرف على الأقل.")
              void accept({ full_name: f.get("full_name"), password })
            }}
          >
            <TextField name="full_name" label="الاسم الكامل" required autoComplete="name" />
            <PasswordField name="password" required autoComplete="new-password" hint="10 أحرف على الأقل." />
            <Button type="submit" size="lg" className="w-full" disabled={busy}>
              {busy ? <Spinner className="size-4" /> : null}
              إنشاء الحساب وقبول الدعوة
            </Button>
          </form>
        )}
      </div>
    </AuthCard>
  )
}

export default function InvitePage() {
  return (
    <Suspense>
      <Invite />
    </Suspense>
  )
}
