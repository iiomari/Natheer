"use client"

import { useState } from "react"
import { BadgeCheck, MailWarning, MoreHorizontal, UserPlus, Users } from "lucide-react"
import { toast } from "sonner"

import { CopyLink } from "@/components/data"
import { EmailField, Field, NativeSelect } from "@/components/form"
import { AdminOnly, LoadError, Loading, useCurrentMembership } from "@/components/org"
import { Chip, EmptyState, InlineError, Ltr, PageHeader, Section, Spinner } from "@/components/nz"
import { Button } from "@/components/ui/button"
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog"
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu"
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table"
import { api, messageFor } from "@/lib/api"
import { useSession } from "@/lib/session"
import type { Invitation, Member, Role } from "@/lib/types"
import { formatDay, useApi } from "@/lib/use-api"

function RoleChip({ m }: { m: Pick<Member, "role" | "data_manager"> }) {
  if (m.role === "admin") return <Chip tone="primary">مدير</Chip>
  if (m.data_manager) return <Chip tone="twin">مدير بيانات</Chip>
  return <Chip>عضو</Chip>
}

function InviteDialog({ orgId, open, onOpenChange, onDone }: {
  orgId: string
  open: boolean
  onOpenChange: (v: boolean) => void
  onDone: () => void
}) {
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)
  const [link, setLink] = useState<string | null>(null)

  function close(v: boolean) {
    onOpenChange(v)
    if (!v) {
      setLink(null)
      setError(null)
    }
  }

  async function onSubmit(e: React.FormEvent<HTMLFormElement>) {
    e.preventDefault()
    const f = new FormData(e.currentTarget)
    const role = String(f.get("role")) as "admin" | "member" | "data_manager"
    setBusy(true)
    setError(null)
    try {
      const res = await api<{ link_path: string }>(`/orgs/${orgId}/invitations`, {
        method: "POST",
        body: { email: f.get("email"), role: role === "admin" ? "admin" : "member", data_manager: role === "data_manager" },
      })
      setLink(res.link_path)
      onDone()
    } catch (err) {
      setError(messageFor(err))
    } finally {
      setBusy(false)
    }
  }

  return (
    <Dialog open={open} onOpenChange={close}>
      <DialogContent className="sm:max-w-lg">
        <DialogHeader>
          <DialogTitle className="text-lg">دعوة عضو</DialogTitle>
          <DialogDescription>
            {link
              ? "انسخ الرابط وأرسله للعضو بالطريقة التي تناسبك. يظهر الرابط مرة واحدة، وصالح 7 أيام."
              : "سننشئ رابط دعوة تنسخه وترسله بنفسك. فتح الرابط وإنشاء الحساب يؤكّد العضو."}
          </DialogDescription>
        </DialogHeader>
        {link ? (
          <>
            <CopyLink path={link} label="رابط الدعوة" />
            <DialogFooter>
              <Button onClick={() => close(false)}>تم</Button>
            </DialogFooter>
          </>
        ) : (
        <>
        <form id="invite-form" onSubmit={onSubmit} className="space-y-5" noValidate>
          {error ? <InlineError>{error}</InlineError> : null}
          <EmailField name="email" required autoFocus />
          <Field label="الدور" hint="مدير البيانات يرفع وينظّف ويولّد ويشارك، ولا يملك إعادة الربط.">
            <NativeSelect name="role" defaultValue="member">
              <option value="member">عضو: يستلم البيانات ويعيد النتائج</option>
              <option value="data_manager">مدير بيانات</option>
              <option value="admin">مدير المنشأة: صلاحيات كاملة</option>
            </NativeSelect>
          </Field>
        </form>
        <DialogFooter>
          <Button variant="outline" onClick={() => close(false)}>إلغاء</Button>
          <Button type="submit" form="invite-form" disabled={busy}>
            {busy ? <Spinner className="size-4" /> : null}
            إنشاء رابط الدعوة
          </Button>
        </DialogFooter>
        </>
        )}
      </DialogContent>
    </Dialog>
  )
}

function ConfirmRemove({ member, onCancel, onConfirm, busy }: {
  member: Member | null
  onCancel: () => void
  onConfirm: () => void
  busy: boolean
}) {
  return (
    <Dialog open={member !== null} onOpenChange={(v) => !v && onCancel()}>
      <DialogContent className="sm:max-w-md">
        <DialogHeader>
          <DialogTitle className="text-lg">إزالة عضو</DialogTitle>
          <DialogDescription>
            سيفقد <strong>{member?.full_name}</strong> الوصول إلى مساحة المنشأة فوراً. يُسجَّل الإجراء في سجل التدقيق.
          </DialogDescription>
        </DialogHeader>
        <DialogFooter>
          <Button variant="outline" onClick={onCancel}>إلغاء</Button>
          <Button variant="destructive" onClick={onConfirm} disabled={busy}>
            {busy ? <Spinner className="size-4" /> : null}
            إزالة
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}

export default function TeamPage() {
  const { me, refresh } = useSession()
  const { orgId, membership } = useCurrentMembership()
  const isAdmin = membership?.role === "admin"
  const members = useApi<Member[]>(isAdmin ? `/orgs/${orgId}/members` : null)
  const invites = useApi<Invitation[]>(isAdmin ? `/orgs/${orgId}/invitations` : null)
  const [inviteOpen, setInviteOpen] = useState(false)
  const [removing, setRemoving] = useState<Member | null>(null)
  const [reset, setReset] = useState<{ name: string; path: string } | null>(null)
  const [busy, setBusy] = useState(false)

  if (!isAdmin) return <AdminOnly />

  async function patch(m: Member, body: { role?: Role; data_manager?: boolean }) {
    try {
      await api(`/orgs/${orgId}/members/${m.id}`, { method: "PATCH", body })
      toast.success("حُدّث الدور.")
      await members.reload()
      if (m.user_id === me?.id) await refresh()
    } catch (e) {
      toast.error(messageFor(e))
    }
  }

  async function remove() {
    if (!removing) return
    setBusy(true)
    try {
      await api(`/orgs/${orgId}/members/${removing.id}`, { method: "DELETE" })
      toast.success("أُزيل العضو.")
      setRemoving(null)
      await members.reload()
    } catch (e) {
      toast.error(messageFor(e))
    } finally {
      setBusy(false)
    }
  }

  async function resetLink(m: Member) {
    try {
      const r = await api<{ link_path: string }>(`/orgs/${orgId}/members/${m.id}/reset-link`, { method: "POST" })
      setReset({ name: m.full_name, path: r.link_path })
    } catch (e) {
      toast.error(messageFor(e))
    }
  }

  async function revoke(inv: Invitation) {
    try {
      await api(`/orgs/${orgId}/invitations/${inv.id}`, { method: "DELETE" })
      toast.success("أُلغيت الدعوة.")
      await invites.reload()
    } catch (e) {
      toast.error(messageFor(e))
    }
  }

  return (
    <>
      <PageHeader
        title="الفريق"
        description="من يدخل مساحة المنشأة، وبأي صلاحية."
        actions={
          <Button onClick={() => setInviteOpen(true)}>
            <UserPlus data-icon="inline-start" />
            دعوة عضو
          </Button>
        }
      />

      <Section title="الأعضاء">
        {members.loading ? (
          <Loading />
        ) : members.error ? (
          <LoadError error={members.error} />
        ) : (
          <div className="overflow-x-auto rounded-xl border border-border bg-card shadow-card">
            <Table>
              <TableHeader className="sticky top-0 bg-muted/60">
                <TableRow>
                  <TableHead className="h-11 px-5 text-start font-bold">الاسم</TableHead>
                  <TableHead className="h-11 px-5 text-start font-bold">البريد</TableHead>
                  <TableHead className="h-11 px-5 text-start font-bold">الدور</TableHead>
                  <TableHead className="h-11 px-5 text-start font-bold">الحساب</TableHead>
                  <TableHead className="h-11 px-5 text-start font-bold">انضم</TableHead>
                  <TableHead className="h-11 w-12 px-5"><span className="sr-only">إجراءات</span></TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {members.data?.map((m) => (
                  <TableRow key={m.id}>
                    <TableCell className="px-5 py-3.5 font-semibold">
                      {m.full_name}
                      {m.user_id === me?.id ? <span className="ms-2 text-xs text-muted-foreground">(أنت)</span> : null}
                    </TableCell>
                    <TableCell className="px-5 py-3.5"><Ltr>{m.email}</Ltr></TableCell>
                    <TableCell className="px-5 py-3.5"><RoleChip m={m} /></TableCell>
                    <TableCell className="px-5 py-3.5">
                      {m.email_verified ? (
                        <Chip tone="twin" icon={BadgeCheck}>مؤكَّد بالرابط</Chip>
                      ) : (
                        <Chip tone="neutral" icon={MailWarning}>سجّل بنفسه</Chip>
                      )}
                    </TableCell>
                    <TableCell className="px-5 py-3.5 text-muted-foreground">{formatDay(m.joined_at)}</TableCell>
                    <TableCell className="px-5 py-3.5">
                      <DropdownMenu>
                        <DropdownMenuTrigger render={<Button variant="ghost" size="icon-sm" aria-label={`إجراءات ${m.full_name}`} />}>
                          <MoreHorizontal />
                        </DropdownMenuTrigger>
                        <DropdownMenuContent align="end" className="w-56">
                          {m.role !== "admin" ? (
                            <DropdownMenuItem onClick={() => patch(m, { role: "admin" })}>تعيين مديراً للمنشأة</DropdownMenuItem>
                          ) : (
                            <DropdownMenuItem onClick={() => patch(m, { role: "member" })}>تحويل إلى عضو</DropdownMenuItem>
                          )}
                          {m.role !== "admin" ? (
                            <DropdownMenuItem onClick={() => patch(m, { data_manager: !m.data_manager })}>
                              {m.data_manager ? "سحب صلاحية مدير البيانات" : "منح صلاحية مدير البيانات"}
                            </DropdownMenuItem>
                          ) : null}
                          {m.user_id !== me?.id ? (
                            <DropdownMenuItem onClick={() => resetLink(m)}>رابط إعادة تعيين كلمة المرور</DropdownMenuItem>
                          ) : null}
                          <DropdownMenuSeparator />
                          <DropdownMenuItem variant="destructive" onClick={() => setRemoving(m)}>إزالة من المنشأة</DropdownMenuItem>
                        </DropdownMenuContent>
                      </DropdownMenu>
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </div>
        )}
      </Section>

      <Section title="دعوات معلّقة" className="mt-10">
        {invites.loading ? (
          <Loading />
        ) : invites.error ? (
          <LoadError error={invites.error} />
        ) : !invites.data?.length ? (
          <EmptyState icon={Users} title="لا توجد دعوات معلّقة" description="الدعوات التي لم تُقبل بعد تظهر هنا." />
        ) : (
          <ul className="divide-y divide-border rounded-xl border border-border bg-card shadow-card">
            {invites.data.map((inv) => (
              <li key={inv.id} className="flex flex-wrap items-center justify-between gap-3 px-5 py-4">
                <div className="flex flex-wrap items-center gap-3">
                  <Ltr className="font-semibold">{inv.email}</Ltr>
                  <RoleChip m={inv} />
                  {inv.expired ? <Chip tone="review">منتهية</Chip> : <span className="text-sm text-muted-foreground">تنتهي {formatDay(inv.expires_at)}</span>}
                </div>
                <Button size="sm" variant="outline" onClick={() => revoke(inv)}>إلغاء الدعوة</Button>
              </li>
            ))}
          </ul>
        )}
      </Section>

      <InviteDialog orgId={orgId} open={inviteOpen} onOpenChange={setInviteOpen} onDone={() => void invites.reload()} />
      <Dialog open={reset !== null} onOpenChange={(v) => !v && setReset(null)}>
        <DialogContent className="sm:max-w-lg">
          <DialogHeader>
            <DialogTitle className="text-lg">رابط إعادة تعيين كلمة المرور</DialogTitle>
            <DialogDescription>
              أرسل الرابط إلى <strong>{reset?.name}</strong>. يُستخدم مرة واحدة، وصالح 24 ساعة، ويُنهي جلساته الحالية.
            </DialogDescription>
          </DialogHeader>
          {reset ? <CopyLink path={reset.path} /> : null}
          <DialogFooter>
            <Button onClick={() => setReset(null)}>تم</Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
      <ConfirmRemove member={removing} onCancel={() => setRemoving(null)} onConfirm={remove} busy={busy} />
    </>
  )
}
