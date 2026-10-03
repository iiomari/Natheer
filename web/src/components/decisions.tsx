"use client"

import { useState } from "react"
import { Check, ChevronDown, ChevronUp, Sparkles } from "lucide-react"
import { toast } from "sonner"

import { Chip, InfoTip, Num, Spinner } from "@/components/nz"
import { Button } from "@/components/ui/button"
import { api, messageFor } from "@/lib/api"
import { type DecisionReason, reasonLine } from "@/lib/labels"
import { useApi } from "@/lib/use-api"
import { cn } from "@/lib/utils"

type Choice = "keep" | "replace"
type Item = { id: string; row: number; before: string; value: string; after: string; final: string; auto: Choice | null;
  admin: Choice | null; reason: DecisionReason }
type Group = { key: string; phrase: string; column: string; kind: string; count: number; population: number; passed: number;
  auto: Choice | null; suggestion: Choice; reason: DecisionReason; admin: Choice | null; final: string; pending: number;
  examples?: Item[]; items?: Item[] }
type Payload = { groups: Group[]; totals: { auto?: number; admin?: number; pending?: number }; session_open: boolean }

const LABEL: Record<Choice, string> = { keep: "أبقِها كما هي", replace: "حوّلها لنظير" }

function Snippet({ it }: { it: Item }) {
  return (
    <span className="leading-7">
      {it.before}<mark className="rounded bg-muted px-1 font-semibold text-foreground"><bdi>{it.value}</bdi></mark>{it.after}
    </span>
  )
}

function Choices({ value, onPick, busy, size = "sm" }: { value: Choice | null; onPick: (c: Choice) => void; busy: boolean; size?: "sm" | "xs" }) {
  return (
    <div className="flex gap-1.5">
      {(["keep", "replace"] as const).map((c) => (
        <Button key={c} size={size} variant={value === c ? "default" : "outline"} disabled={busy} onClick={() => onPick(c)}
          aria-pressed={value === c}>
          {value === c ? <Check data-icon="inline-start" /> : null}{LABEL[c]}
        </Button>
      ))}
    </div>
  )
}

function GroupRow({ orgId, dsId, g, onChanged }: { orgId: string; dsId: string; g: Group; onChanged: () => void }) {
  const [open, setOpen] = useState(false)
  const [busy, setBusy] = useState(false)
  const all = useApi<Payload>(open ? `/orgs/${orgId}/datasets/${dsId}/decisions?group=${encodeURIComponent(g.key)}` : null)
  const items = all.data?.groups.find((x) => x.key === g.key)?.items

  async function save(body: unknown) {
    setBusy(true)
    try {
      await api(`/orgs/${orgId}/datasets/${dsId}/decisions`, { method: "PUT", body })
      onChanged()
      if (open) await all.reload()
    } catch (e) {
      toast.error(messageFor(e))
    } finally {
      setBusy(false)
    }
  }

  const current: Choice | null = g.admin ?? (g.pending ? null : g.auto)
  return (
    <li className="space-y-3 px-5 py-4">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="min-w-0">
          <p className="font-bold">
            {g.phrase ? <>«{g.phrase}»</> : "بلا سياق"} <span className="font-normal text-muted-foreground">· <Num>{g.count}</Num> رقماً · <bdi>{g.column}</bdi></span>
          </p>
          <p className="text-sm text-muted-foreground">
            {g.admin ? "قرارك" : g.auto ? "قرار نَظير" : "اقتراح نَظير"}: <span className="font-semibold text-foreground">{LABEL[g.admin ?? g.auto ?? g.suggestion]}</span>
            {" · "}{reasonLine(g.reason, g.phrase)}
          </p>
        </div>
        <Choices value={current} busy={busy} onPick={(c) => save({ groups: { [g.key]: c } })} />
      </div>
      {g.examples?.length ? (
        <ul className="space-y-1 text-sm text-muted-foreground">
          {g.examples.map((it) => <li key={it.id}><Snippet it={it} /></li>)}
        </ul>
      ) : null}
      <div className="flex flex-wrap items-center gap-3">
        <button type="button" onClick={() => setOpen(!open)} className="inline-flex items-center gap-1 text-sm font-semibold text-primary">
          {open ? <ChevronUp className="size-4" /> : <ChevronDown className="size-4" />} كل القيم
        </button>
        {g.admin ? (
          <button type="button" disabled={busy} onClick={() => save({ groups: { [g.key]: null } })} className="text-sm text-muted-foreground underline">
            تراجع عن قرارك
          </button>
        ) : null}
      </div>
      {open ? (
        items ? (
          <ul className="max-h-80 divide-y divide-border overflow-auto rounded-lg border border-border">
            {items.map((it) => (
              <li key={it.id} className="flex flex-wrap items-center justify-between gap-2 px-3 py-2 text-sm">
                <span className="min-w-0"><Num className="me-2 text-xs text-muted-foreground">{it.row}</Num><Snippet it={it} /></span>
                <Choices size="xs" value={(it.admin ?? (it.final === "pending" ? null : it.final)) as Choice | null} busy={busy}
                  onPick={(c) => save({ values: { [g.key]: { [it.id]: c } } })} />
              </li>
            ))}
          </ul>
        ) : <Spinner className="size-4" />
      ) : null}
    </li>
  )
}

/** Decisions on uncertain values: Nazeer decides most from evidence; the admin decides the rest. */
export function Decisions({ orgId, dsId, onChanged }: { orgId: string; dsId: string; onChanged: () => void }) {
  const d = useApi<Payload>(`/orgs/${orgId}/datasets/${dsId}/decisions`)
  const [showAuto, setShowAuto] = useState(false)
  const [busy, setBusy] = useState(false)
  if (!d.data || !d.data.groups.length) return null
  const waiting = d.data.groups.filter((g) => g.pending > 0)
  const decided = d.data.groups.filter((g) => g.pending === 0)
  const t = d.data.totals
  const refresh = () => { void d.reload(); onChanged() }

  async function acceptAll() {
    setBusy(true)
    try {
      await api(`/orgs/${orgId}/datasets/${dsId}/decisions/accept`, { method: "POST" })
      refresh()
    } catch (e) {
      toast.error(messageFor(e))
    } finally {
      setBusy(false)
    }
  }

  return (
    <section className="space-y-3" aria-labelledby="decisions-h">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <h2 id="decisions-h" className="flex items-center gap-2 text-lg font-bold">
          القرارات
          <InfoTip>أرقام تجتاز خوارزمية الهوية في سياق غير واضح. يقرر نَظير من الإحصاء: الأرقام العشوائية تجتازها بنسبة ١٠٪ تقريباً، والهويات بنسبة ١٠٠٪.</InfoTip>
        </h2>
        <p className="text-sm text-muted-foreground">
          <Num>{t.auto ?? 0}</Num> اتخذها نَظير · <Num>{t.admin ?? 0}</Num> بقرارك · <Num>{t.pending ?? 0}</Num> بانتظارك
        </p>
      </div>
      {waiting.length ? (
        <div className="rounded-xl border border-primary/20 bg-accent/60 shadow-card">
          <div className="flex flex-wrap items-center justify-between gap-3 border-b border-primary/15 px-5 py-3">
            <p className="font-bold">قرارات بانتظارك</p>
            <Button size="sm" onClick={acceptAll} disabled={busy}>
              {busy ? <Spinner className="size-4" /> : <Sparkles data-icon="inline-start" />} طبّق اقتراحات نَظير
            </Button>
          </div>
          <ul className="divide-y divide-border bg-card">
            {waiting.map((g) => <GroupRow key={g.key} orgId={orgId} dsId={dsId} g={g} onChanged={refresh} />)}
          </ul>
        </div>
      ) : null}
      {decided.length ? (
        <div className="rounded-xl border border-border bg-card shadow-card">
          <button type="button" onClick={() => setShowAuto(!showAuto)} aria-expanded={showAuto}
            className={cn("flex w-full items-center justify-between px-5 py-3 text-start font-semibold", showAuto && "border-b border-border")}>
            <span>قرارات اتخذها نَظير <span className="text-muted-foreground">(<Num>{decided.length}</Num> مجموعة)</span></span>
            {showAuto ? <ChevronUp className="size-4" /> : <ChevronDown className="size-4" />}
          </button>
          {showAuto ? <ul className="divide-y divide-border">{decided.map((g) => <GroupRow key={g.key} orgId={orgId} dsId={dsId} g={g} onChanged={refresh} />)}</ul> : null}
        </div>
      ) : null}
    </section>
  )
}

export function DecisionsChip({ pending }: { pending: number }) {
  return pending ? <Chip tone="primary"><Num>{pending}</Num> بانتظارك</Chip> : null
}
