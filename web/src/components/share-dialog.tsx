"use client"

import { useState } from "react"
import { Plus, X } from "lucide-react"
import { toast } from "sonner"

import { CopyLink } from "@/components/data"
import { Field, NativeSelect } from "@/components/form"
import { InlineError, Ltr, Notice, Spinner } from "@/components/nz"
import { Button } from "@/components/ui/button"
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog"
import { Input } from "@/components/ui/input"
import { api, messageFor } from "@/lib/api"
import { useSession } from "@/lib/session"
import type { Member, ShareInfo } from "@/lib/types"
import { useApi } from "@/lib/use-api"

export function ShareDialog({ orgId, twinId, open, onOpenChange }: {
  orgId: string
  twinId: string
  open: boolean
  onOpenChange: (v: boolean) => void
}) {
  const { me } = useSession()
  const members = useApi<Member[]>(open ? `/orgs/${orgId}/members` : null)
  const [picked, setPicked] = useState<string[]>([])
  const [externals, setExternals] = useState<string[]>([])
  const [draft, setDraft] = useState("")
  const [days, setDays] = useState("7")
  const [formats, setFormats] = useState<("csv" | "xlsx")[]>(["csv", "xlsx"])
  const [message, setMessage] = useState("")
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)
  const [result, setResult] = useState<ShareInfo | null>(null)

  function close(v: boolean) {
    onOpenChange(v)
    if (!v) {
      setResult(null)
      setError(null)
      setPicked([])
      setExternals([])
    }
  }

  async function submit() {
    setBusy(true)
    setError(null)
    try {
      const r = await api<ShareInfo>(`/orgs/${orgId}/twins/${twinId}/shares`, {
        method: "POST",
        body: { member_ids: picked, external_labels: externals, expires_in_days: Number(days), formats, message: message || null },
      })
      setResult(r)
      if (!r.new_links?.length) toast.success("شوركت البيانات مع الأعضاء المختارين.")
    } catch (e) {
      setError(messageFor(e))
    } finally {
      setBusy(false)
    }
  }

  const others = members.data?.filter((m) => m.user_id !== me?.id) ?? []
  return (
    <Dialog open={open} onOpenChange={close}>
      <DialogContent className="max-h-[90vh] overflow-y-auto sm:max-w-xl">
        <DialogHeader>
          <DialogTitle className="text-lg">مشاركة النظير</DialogTitle>
          <DialogDescription>يرى المستلمون النظير فقط.</DialogDescription>
        </DialogHeader>
        {result ? (
          <div className="space-y-5">
            <Notice tone="twin">
              أُنشئت المشاركة.
              {result.new_links?.length ? " أرسل كل رابط لصاحبه؛ يظهر مرة واحدة." : null}
            </Notice>
            {result.new_links?.map((l) => <CopyLink key={l.link_path} path={l.link_path} label={l.label} />)}
            <DialogFooter>
              <Button onClick={() => close(false)}>تم</Button>
            </DialogFooter>
          </div>
        ) : (
          <div className="space-y-6">
            {error ? <InlineError>{error}</InlineError> : null}
            <Field label="أعضاء المنشأة">
              {members.loading ? (
                <Spinner className="size-4" />
              ) : others.length ? (
                <ul className="max-h-48 divide-y divide-border overflow-y-auto rounded-lg border border-border">
                  {others.map((m) => (
                    <li key={m.id}>
                      <label className="flex cursor-pointer items-center gap-3 px-3 py-2.5 text-sm">
                        <input
                          type="checkbox"
                          className="size-4 accent-[var(--primary)]"
                          checked={picked.includes(m.id)}
                          onChange={(e) => setPicked(e.target.checked ? [...picked, m.id] : picked.filter((x) => x !== m.id))}
                        />
                        <span className="font-semibold">{m.full_name}</span>
                        <Ltr className="text-muted-foreground">{m.email}</Ltr>
                      </label>
                    </li>
                  ))}
                </ul>
              ) : (
                <p className="text-sm text-muted-foreground">لا أعضاء آخرون بعد.</p>
              )}
            </Field>
            <Field label="مستلمون خارجيون">
              <div className="flex gap-2">
                <Input
                  value={draft}
                  onChange={(e) => setDraft(e.target.value)}
                  placeholder="اسم أو بريد، مثل شركة التحليل"
                  onKeyDown={(e) => {
                    if (e.key === "Enter" && draft.trim()) {
                      e.preventDefault()
                      setExternals([...externals, draft.trim()])
                      setDraft("")
                    }
                  }}
                />
                <Button type="button" variant="outline" disabled={!draft.trim()} onClick={() => {
                  setExternals([...externals, draft.trim()])
                  setDraft("")
                }}>
                  <Plus data-icon="inline-start" /> إضافة
                </Button>
              </div>
              {externals.length ? (
                <ul className="flex flex-wrap gap-2 pt-1">
                  {externals.map((x, i) => (
                    <li key={i} className="inline-flex items-center gap-1 rounded-full border border-border bg-muted px-3 py-1 text-sm">
                      <bdi>{x}</bdi>
                      <button type="button" aria-label={`إزالة ${x}`} onClick={() => setExternals(externals.filter((_, j) => j !== i))}>
                        <X className="size-3.5" />
                      </button>
                    </li>
                  ))}
                </ul>
              ) : null}
            </Field>
            <div className="grid gap-4 sm:grid-cols-2">
              <Field label="تنتهي بعد">
                <NativeSelect value={days} onChange={(e) => setDays(e.target.value)}>
                  {[1, 3, 7, 14, 30].map((d) => <option key={d} value={d}>{d === 1 ? "يوم واحد" : `${d} أيام`}</option>)}
                </NativeSelect>
              </Field>
              <Field label="الصيغ المسموحة">
                <div className="flex h-10 items-center gap-5">
                  {(["csv", "xlsx"] as const).map((f) => (
                    <label key={f} className="flex items-center gap-2 text-sm font-semibold">
                      <input type="checkbox" className="size-4 accent-[var(--primary)]" checked={formats.includes(f)}
                        onChange={(e) => setFormats(e.target.checked ? [...formats, f] : formats.filter((x) => x !== f))} />
                      {f === "csv" ? "CSV" : "Excel"}
                    </label>
                  ))}
                </div>
              </Field>
            </div>
            <Field label="رسالة">
              <Input value={message} onChange={(e) => setMessage(e.target.value.slice(0, 500))} placeholder="اختياري" />
            </Field>
            <DialogFooter>
              <Button variant="ghost" onClick={() => close(false)}>إلغاء</Button>
              <Button onClick={submit} disabled={busy || !formats.length || (!picked.length && !externals.length)}>
                {busy ? <Spinner className="size-4" /> : null}
                مشاركة
              </Button>
            </DialogFooter>
          </div>
        )}
      </DialogContent>
    </Dialog>
  )
}
