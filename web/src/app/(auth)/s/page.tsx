"use client"

import Link from "next/link"
import { useRouter, useSearchParams } from "next/navigation"
import { Suspense, useEffect, useRef, useState } from "react"
import { Inbox } from "lucide-react"

import { AuthCard } from "@/components/auth-card"
import { InlineError, Ltr, Notice, Spinner } from "@/components/nz"
import { Button, buttonVariants } from "@/components/ui/button"
import { ApiError, api, messageFor } from "@/lib/api"
import type { Me } from "@/lib/types"
import { TOKEN_RULE } from "@/components/returns"
import { formatDay } from "@/lib/use-api"

type Preview = { org_name: string; dataset_name: string; status: "active" | "expired" | "revoked"; expires_at: string; accepted: boolean }

/** A share link: the recipient signs in (or creates an account) and accepts it; that binds the share to them. */
function ShareLink() {
  const router = useRouter()
  const token = useSearchParams().get("token") ?? ""
  const [preview, setPreview] = useState<Preview | null>(null)
  const [me, setMe] = useState<Me | null>(null)
  const [error, setError] = useState<string | null>(token ? null : "الرابط غير مكتمل.")
  const [loading, setLoading] = useState(Boolean(token))
  const [busy, setBusy] = useState(false)
  const started = useRef(false)

  useEffect(() => {
    if (!token || started.current) return
    started.current = true
    Promise.all([
      api<Preview>("/share-links/preview", { method: "POST", body: { token } }),
      api<Me>("/auth/me").catch((e) => (e instanceof ApiError && e.status === 401 ? null : Promise.reject(e))),
    ])
      .then(([p, m]) => {
        setPreview(p)
        setMe(m)
      })
      .catch((e) => setError(messageFor(e)))
      .finally(() => setLoading(false))
  }, [token])

  async function accept() {
    setBusy(true)
    setError(null)
    try {
      const r = await api<{ share_id: string }>("/share-links/accept", { method: "POST", body: { token } })
      router.replace(`/app/received/${r.share_id}`)
    } catch (e) {
      setError(messageFor(e))
      setBusy(false)
    }
  }

  const back = encodeURIComponent(`/s?token=${token}`)
  return (
    <AuthCard
      title={preview ? `بيانات مشاركة من ${preview.org_name}` : "رابط مشاركة"}
      description={preview ? <>«{preview.dataset_name}» · تنتهي {formatDay(preview.expires_at)}</> : undefined}
    >
      {loading ? (
        <div className="flex items-center gap-3 text-muted-foreground"><Spinner className="size-4" /> نتحقق من الرابط…</div>
      ) : !preview ? (
        <InlineError>{error ?? "الرابط غير صالح."}</InlineError>
      ) : preview.status !== "active" ? (
        <InlineError>{preview.status === "expired" ? "انتهت صلاحية هذه المشاركة." : "ألغت المنشأة هذه المشاركة."}</InlineError>
      ) : (
        <div className="space-y-5">
          <Notice icon={Inbox}>هذه بيانات نظيرة لا تحتوي أي شخص حقيقي. يعمل الرابط لحساب واحد فقط.</Notice>
          <p className="text-sm leading-7 text-muted-foreground">{TOKEN_RULE}</p>
          {error ? <InlineError>{error}</InlineError> : null}
          {me ? (
            <>
              <p className="text-sm text-muted-foreground">ستُضاف المشاركة إلى حسابك <Ltr>{me.email}</Ltr>.</p>
              <Button size="lg" className="w-full" onClick={accept} disabled={busy}>
                {busy ? <Spinner className="size-4" /> : null}
                قبول واستعراض البيانات
              </Button>
            </>
          ) : (
            <div className="grid gap-3">
              <Link href={`/login?next=${back}`} className={buttonVariants({ size: "lg", className: "w-full" })}>تسجيل الدخول للقبول</Link>
              <Link href={`/signup?next=${back}`} className={buttonVariants({ size: "lg", variant: "outline", className: "w-full" })}>إنشاء حساب فرد</Link>
            </div>
          )}
        </div>
      )}
    </AuthCard>
  )
}

export default function ShareLinkPage() {
  return (
    <Suspense>
      <ShareLink />
    </Suspense>
  )
}
