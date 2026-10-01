"use client"

import { useState } from "react"
import { KeyRound } from "lucide-react"
import { toast } from "sonner"

import { TextField } from "@/components/form"
import { AdminOnly, LoadError, Loading, useCurrentMembership } from "@/components/org"
import { Chip, Num, PageHeader, Section, Spinner } from "@/components/nz"
import { Button } from "@/components/ui/button"
import { api, messageFor } from "@/lib/api"
import { useSession } from "@/lib/session"
import type { Org } from "@/lib/types"
import { useApi } from "@/lib/use-api"

export default function SettingsPage() {
  const { refresh } = useSession()
  const { orgId, membership } = useCurrentMembership()
  const isAdmin = membership?.role === "admin"
  const org = useApi<Org>(isAdmin ? `/orgs/${orgId}` : null)
  const [busy, setBusy] = useState(false)
  if (!isAdmin) return <AdminOnly />

  async function onSubmit(e: React.FormEvent<HTMLFormElement>) {
    e.preventDefault()
    setBusy(true)
    try {
      const updated = await api<Org>(`/orgs/${orgId}`, { method: "PATCH", body: { name: new FormData(e.currentTarget).get("name") } })
      org.setData(updated)
      await refresh()
      toast.success("حُفظ اسم المنشأة.")
    } catch (err) {
      toast.error(messageFor(err))
    } finally {
      setBusy(false)
    }
  }

  return (
    <>
      <PageHeader title="الإعدادات" description="ملف المنشأة ومفتاحها السري." />
      {org.loading ? (
        <Loading />
      ) : org.error ? (
        <LoadError error={org.error} />
      ) : org.data ? (
        <div className="grid gap-6 lg:grid-cols-2">
          <Section className="rounded-xl border border-border bg-card p-6 shadow-card" title="ملف المنشأة">
            <form onSubmit={onSubmit} className="space-y-5">
              <TextField name="name" label="اسم المنشأة" defaultValue={org.data.name} required minLength={2} maxLength={160} />
              <Button type="submit" disabled={busy}>
                {busy ? <Spinner className="size-4" /> : null}
                حفظ
              </Button>
            </form>
          </Section>
          <Section className="rounded-xl border border-border bg-card p-6 shadow-card" title="مفتاح المنشأة">
            <div className="flex items-start gap-4">
              <span className="grid size-10 shrink-0 place-items-center rounded-lg bg-accent text-accent-foreground">
                <KeyRound className="size-5" aria-hidden="true" />
              </span>
              <div className="space-y-2 text-[0.9375rem] leading-7">
                <p>
                  مفتاح سري خاص بمنشأتك يولّد البدائل نفسها في كل مرة، ويتيح لمدير المنشأة وحده إعادة ربط النتائج.
                  لا يُعرض المفتاح ولا يغادر الخادم.
                </p>
                <p className="flex items-center gap-2 text-sm text-muted-foreground">
                  الإصدار الحالي: <Num>{org.data.key_version}</Num>
                  <Chip>التدوير قريباً</Chip>
                </p>
              </div>
            </div>
          </Section>
        </div>
      ) : null}
    </>
  )
}
