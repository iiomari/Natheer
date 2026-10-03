"use client"

import { useEffect, useMemo, useState } from "react"
import { Eye, RotateCcw, Sparkles } from "lucide-react"
import { toast } from "sonner"

import { Chip, InfoTip, InlineError, Ltr, Notice, Num, Section, Spinner } from "@/components/nz"
import { Button } from "@/components/ui/button"
import { Checkbox } from "@/components/ui/checkbox"
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table"
import { api, messageFor } from "@/lib/api"
import type { CleanExample, CleanOptions, CleanRule, CleanSuggestion, Dataset } from "@/lib/types"
import { cn } from "@/lib/utils"

export const RULES: { id: CleanRule; label: string; text: string; unit: string }[] = [
  { id: "trim", label: "المسافات والمحارف الخفية", text: "حذف المسافات الزائدة في الأطراف وبين الكلمات، والمحارف غير المرئية.", unit: "خلية" },
  { id: "nulls", label: "القيم الفارغة", text: "الخلايا التي كلها NULL أو N/A أو - أو «لا يوجد» تصبح فارغة. النصوص التي تحويها لا تُمس.", unit: "خلية" },
  { id: "numbers", label: "أرقام مخزّنة كنص", text: "الأرقام الهندية وفواصل الآلاف تصبح أرقاماً عادية في الأعمدة الرقمية فقط. الهويات والأرقام ذات الأصفار البادئة لا تُمس.", unit: "خلية" },
  { id: "dates", label: "توحيد التواريخ", text: "تتحول التواريخ إلى صيغة YYYY-MM-DD حين يكون ترتيب اليوم والشهر مؤكداً.", unit: "خلية" },
  { id: "dedupe", label: "الصفوف المكررة تماماً", text: "حذف الصف المطابق لصف آخر في كل خلية.", unit: "صف" },
  { id: "arabic", label: "توحيد الحروف العربية", text: "أ إ آ ← ا، ة ← ه، ى ← ي في الأعمدة الفئوية فقط، ولا يُطبَّق على الأسماء أبداً.", unit: "خلية" },
  { id: "phones", label: "توحيد صيغة الجوال", text: "‎+966 و 00966 و 966 تصبح 05XXXXXXXX في أعمدة الجوال.", unit: "خلية" },
]

export const RULE_LABEL: Record<string, string> = {
  ...Object.fromEntries(RULES.map((r) => [r.id, r.label])),
  merges: "دمج تهجئات الفئات المعتمدة",
}

function optionsFrom(ds: Dataset): CleanOptions {
  const c = ds.summary!.cleaning!
  const o = c.report.options
  return {
    trim: o.trim, nulls: o.nulls, numbers: o.numbers, dates: o.dates, dedupe: o.dedupe, arabic: o.arabic, phones: o.phones,
    merges: c.suggestions.filter((g) => g.approved).map((g) => g.key),
  }
}

function Examples({ orgId, ds, rule }: { orgId: string; ds: Dataset; rule: CleanRule }) {
  const [rows, setRows] = useState<CleanExample[] | null>(null)
  const [err, setErr] = useState<string | null>(null)
  useEffect(() => {
    let alive = true
    api<{ examples: CleanExample[] }>(`/orgs/${orgId}/datasets/${ds.id}/cleaning/examples/${rule}`)
      .then((r) => alive && setRows(r.examples))
      .catch((e) => alive && setErr(messageFor(e)))
    return () => {
      alive = false
    }
  }, [orgId, ds.id, rule])
  if (err) return <InlineError>{err}</InlineError>
  if (!rows) return <Spinner className="size-4" />
  if (!rows.length) return <p className="text-sm text-muted-foreground">لا شيء تغيّره هذه القاعدة في بياناتك.</p>
  if (rule === "dedupe")
    return (
      <ul className="text-sm">
        {rows.map((r) => (
          <li key={r.table}><Ltr>{r.table}</Ltr>: <Num>{r.before}</Num> صف مكرر</li>
        ))}
      </ul>
    )
  return (
    <div className="overflow-x-auto rounded-lg border border-border">
      <Table>
        <TableHeader className="bg-muted/60">
          <TableRow>
            <TableHead className="px-4 text-start font-bold">العمود</TableHead>
            <TableHead className="px-4 text-start font-bold">قبل</TableHead>
            <TableHead className="px-4 text-start font-bold">بعد</TableHead>
          </TableRow>
        </TableHeader>
        <TableBody>
          {rows.map((r, i) => (
            <TableRow key={i}>
              <TableCell className="px-4 py-2 text-muted-foreground"><Ltr>{r.table}.{r.column}</Ltr></TableCell>
              <TableCell className="px-4 py-2"><bdi className="rounded bg-sensitive-soft px-1.5 whitespace-pre">{r.before ?? "∅"}</bdi></TableCell>
              <TableCell className="px-4 py-2"><bdi className="rounded bg-twin-soft px-1.5 whitespace-pre">{r.after ?? "(فارغ)"}</bdi></TableCell>
            </TableRow>
          ))}
        </TableBody>
      </Table>
    </div>
  )
}

function Suggestions({ orgId, ds, merges, setMerges, disabled }: {
  orgId: string; ds: Dataset; merges: string[]; setMerges: (m: string[]) => void; disabled: boolean
}) {
  const [groups, setGroups] = useState<CleanSuggestion[] | null>(null)
  const [err, setErr] = useState<string | null>(null)
  useEffect(() => {
    let alive = true
    api<CleanSuggestion[]>(`/orgs/${orgId}/datasets/${ds.id}/cleaning/suggestions`)
      .then((g) => alive && setGroups(g))
      .catch((e) => alive && setErr(messageFor(e)))
    return () => {
      alive = false
    }
  }, [orgId, ds.id])
  if (err) return <InlineError>{err}</InlineError>
  if (!groups) return <Spinner className="size-4" />
  return (
    <ul className="divide-y divide-border">
      {groups.map((g) => {
        const on = merges.includes(g.key)
        return (
          <li key={g.key} className="flex items-start gap-3 py-3">
            <Checkbox
              aria-label={`دمج تهجئات ${g.to}`}
              checked={on}
              disabled={disabled}
              onCheckedChange={(v) => setMerges(v ? [...merges, g.key] : merges.filter((k) => k !== g.key))}
              className="mt-1"
            />
            <div className="text-sm leading-7">
              <span className="text-muted-foreground"><Ltr>{g.table}.{g.column}</Ltr> · </span>
              {g.from.map((f) => <bdi key={f} className="me-1 rounded bg-muted px-1.5">{f}</bdi>)}
              ← <bdi className="rounded bg-twin-soft px-1.5 font-semibold">{g.to}</bdi>
              <span className="ms-2 text-muted-foreground">(<Num>{g.rows}</Num> صف)</span>
            </div>
          </li>
        )
      })}
    </ul>
  )
}

export function CleaningPanel({ orgId, ds, onApplied }: { orgId: string; ds: Dataset; onApplied: () => void }) {
  const c = ds.summary?.cleaning
  const initial = useMemo(() => (c ? optionsFrom(ds) : null), [c, ds])
  const [opts, setOpts] = useState<CleanOptions | null>(initial)
  const [open, setOpen] = useState<CleanRule | null>(null)
  const [busy, setBusy] = useState(false)
  useEffect(() => {
    // eslint-disable-next-line react-hooks/set-state-in-effect
    setOpts(initial)
  }, [initial])
  if (!c || !opts || !initial) return null

  const editable = ds.session_open
  const dirty = JSON.stringify({ ...opts, merges: [...opts.merges].sort() }) !== JSON.stringify({ ...initial, merges: [...initial.merges].sort() })
  const applied = c.report.applied
  const changed = Object.values(applied).reduce((n, r) => n + r.total, 0)

  async function apply() {
    setBusy(true)
    try {
      await api(`/orgs/${orgId}/datasets/${ds.id}/clean`, { method: "POST", body: opts })
      toast.success("يُعاد التنظيف والكشف بالخيارات الجديدة.")
      onApplied()
    } catch (e) {
      toast.error(messageFor(e))
    } finally {
      setBusy(false)
    }
  }

  return (
    <Section
      title="تنظيف البيانات"
      description="يجري قبل الكشف. كل قاعدة اختيارية، ولا شيء يغيّر معنى قيمة. ما طُبِّق يُذكر في تقرير النظير ليعرفه المستلم."
      actions={<Chip tone={changed ? "twin" : "neutral"}><Num>{changed.toLocaleString("en")}</Num> تغيير</Chip>}
    >
      <div className="rounded-xl border border-border bg-card shadow-card">
        <ul className="divide-y divide-border">
          {RULES.map((r) => {
            const on = opts[r.id]
            const done = applied[r.id]?.total ?? 0
            const would = c.potential[r.id] ?? 0
            return (
              <li key={r.id} className="px-5 py-4">
                <div className="flex flex-wrap items-start justify-between gap-3">
                  <label className={cn("flex items-start gap-3", editable && "cursor-pointer")}>
                    <Checkbox
                      checked={on}
                      disabled={!editable}
                      onCheckedChange={(v) => setOpts({ ...opts, [r.id]: Boolean(v) })}
                      className="mt-1"
                    />
                    <span>
                      <span className="font-bold">{r.label}</span>
                      <span className="block text-sm leading-6 text-muted-foreground">{r.text}</span>
                    </span>
                  </label>
                  <span className="flex items-center gap-2">
                    {initial[r.id] ? (
                      <Chip tone={done ? "twin" : "neutral"}>طُبِّق على <Num>{done.toLocaleString("en")}</Num> {r.unit}</Chip>
                    ) : (
                      <Chip tone="neutral">سيغيّر <Num>{would.toLocaleString("en")}</Num> {r.unit}</Chip>
                    )}
                    {editable && would ? (
                      <Button variant="ghost" size="sm" onClick={() => setOpen(open === r.id ? null : r.id)} aria-expanded={open === r.id}>
                        <Eye data-icon="inline-start" /> قبل / بعد
                      </Button>
                    ) : null}
                  </span>
                </div>
                {open === r.id ? <div className="mt-3"><Examples orgId={orgId} ds={ds} rule={r.id} /></div> : null}
              </li>
            )
          })}
        </ul>
      </div>

      {c.report.ambiguous_dates.length ? (
        <Notice tone="review">
          تُركت تواريخ هذه الأعمدة كما هي لأن ترتيب اليوم والشهر غير مؤكد: <Ltr>{c.report.ambiguous_dates.join(", ")}</Ltr>
        </Notice>
      ) : null}

      {c.suggestions.length ? (
        <div className="rounded-xl border border-border bg-card p-5 shadow-card">
          <p className="font-bold">اقتراحات توحيد الفئات</p>
          <p className="mb-2 text-sm text-muted-foreground">تهجئات مختلفة للقيمة نفسها. لا يُدمج شيء إلا ما تعتمده أنت.</p>
          {editable ? (
            <Suggestions orgId={orgId} ds={ds} merges={opts.merges} setMerges={(m) => setOpts({ ...opts, merges: m })} disabled={!editable} />
          ) : (
            <p className="text-sm">اعتُمد <Num>{initial.merges.length}</Num> من <Num>{c.suggestions.length}</Num> اقتراحاً.</p>
          )}
        </div>
      ) : null}

      {c.report_only.length ? (
        <div className="overflow-x-auto rounded-xl border border-border bg-card shadow-card">
          <div className="border-b border-border px-5 py-3">
            <p className="font-bold">ملاحظات للعلم فقط</p>
            <p className="text-sm text-muted-foreground">لا يغيّرها نَظير؛ قد تستحق المراجعة في المصدر.</p>
          </div>
          <Table>
            <TableHeader className="bg-muted/60">
              <TableRow>
                <TableHead className="px-5 text-start font-bold">العمود</TableHead>
                <TableHead className="px-5 text-start font-bold">قيم مفقودة</TableHead>
                <TableHead className="px-5 text-start font-bold">قيم متطرفة</TableHead>
                <TableHead className="px-5 text-start font-bold">أنواع مختلطة</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {c.report_only.map((r) => (
                <TableRow key={`${r.table}.${r.column}`}>
                  <TableCell className="px-5 py-2.5 font-semibold"><Ltr>{r.table}.{r.column}</Ltr></TableCell>
                  <TableCell className="px-5 py-2.5">
                    {r.missing ? <><Num>{r.missing.toLocaleString("en")}</Num> <span className="text-muted-foreground">(<Num>{Math.round(r.missing_share * 100)}%</Num>)</span></> : "—"}
                  </TableCell>
                  <TableCell className="px-5 py-2.5">{r.extreme_outliers ? <Num>{r.extreme_outliers}</Num> : "—"}</TableCell>
                  <TableCell className="px-5 py-2.5">{r.mixed_types ? <Chip tone="review">أرقام ونصوص</Chip> : "—"}</TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </div>
      ) : null}

      {editable ? (
        <div className="flex flex-wrap gap-3">
          <Button onClick={apply} disabled={!dirty || busy}>
            {busy ? <Spinner className="size-4" /> : <Sparkles data-icon="inline-start" />}
            طبّق وأعد الكشف
          </Button>
          {dirty ? (
            <Button variant="ghost" onClick={() => setOpts(initial)}>
              <RotateCcw data-icon="inline-start" /> تراجع
            </Button>
          ) : null}
        </div>
      ) : null}
    </Section>
  )
}

export function CleaningNote({ cleaning }: { cleaning: { rules: string[]; changed: Record<string, number> } | null | undefined }) {
  if (!cleaning) return null
  const done = cleaning.rules.filter((r) => (cleaning.changed[r] ?? 0) > 0)
  return (
    <Section title="ما نُظِّف قبل التوليد">
      {done.length ? (
        <ul className="grid gap-2 sm:grid-cols-2">
          {done.map((r) => (
            <li key={r} className="flex items-center justify-between gap-3 rounded-lg border border-border bg-card px-4 py-2.5 text-sm">
              <span>{RULE_LABEL[r] ?? r}</span>
              <Num>{cleaning.changed[r].toLocaleString("en")}</Num>
            </li>
          ))}
        </ul>
      ) : (
        <p className="text-sm text-muted-foreground">لا شيء.</p>
      )}
    </Section>
  )
}

/** Cleaning is optional: one line when nothing is needed; «نظّف» / «تخطَّ» when something could be;
 * the rule toggles only behind «خيارات التنظيف». */
export function CleaningStep({ orgId, ds, onApplied }: { orgId: string; ds: Dataset; onApplied: () => void }) {
  const c = ds.summary?.cleaning
  const [open, setOpen] = useState(false)
  const [busy, setBusy] = useState<"clean" | "skip" | null>(null)
  if (!c) return null
  const decision = c.decision ?? "applied"
  const changed = Object.values(c.report.applied).reduce((n, r) => n + (r?.total ?? 0), 0)

  async function act(kind: "clean" | "skip") {
    setBusy(kind)
    try {
      if (kind === "clean") {
        await api(`/orgs/${orgId}/datasets/${ds.id}/clean`, { method: "POST", body: {} })
        toast.success("يُنظَّف الملف ويُعاد الكشف.")
      } else {
        await api(`/orgs/${orgId}/datasets/${ds.id}/cleaning/skip`, { method: "POST" })
      }
      onApplied()
    } catch (e) {
      toast.error(messageFor(e))
    } finally {
      setBusy(null)
    }
  }

  const line =
    decision === "not_needed" ? <><span className="font-bold text-twin">البيانات نظيفة</span> — لا حاجة للتنظيف.</>
    : decision === "pending" ? <span className="inline-flex items-center gap-1.5"><span className="font-bold">يمكن تنظيف <Num>{(c.recommended ?? 0).toLocaleString("en")}</Num> خلية</span> · اختياري
        <InfoTip>مسافات زائدة، قيم فارغة، أرقام وتواريخ بصيغ مختلفة، صفوف مكررة. لا يتغيّر معنى أي قيمة.</InfoTip></span>
    : decision === "skipped" ? <>تخطّيتَ التنظيف: تُستخدم البيانات كما رُفعت.</>
    : <><span className="font-bold text-twin">نُظِّف الملف</span>: تغيّرت <Num>{changed.toLocaleString("en")}</Num> قيمة.</>

  return (
    <div className="space-y-4">
      <div className={cn("flex flex-wrap items-center justify-between gap-3 rounded-xl border px-5 py-4 shadow-card",
        decision === "pending" ? "border-primary/20 bg-accent/60" : "border-border bg-card")}>
        <p className="text-sm leading-7">{line}</p>
        <div className="flex flex-wrap items-center gap-2">
          {decision === "pending" && ds.session_open ? (
            <>
              <Button size="sm" onClick={() => act("clean")} disabled={busy !== null}>
                {busy === "clean" ? <Spinner className="size-4" /> : <Sparkles data-icon="inline-start" />} نظّف
              </Button>
              <Button size="sm" variant="outline" onClick={() => act("skip")} disabled={busy !== null}>تخطَّ</Button>
            </>
          ) : null}
          <Button size="sm" variant="ghost" onClick={() => setOpen(!open)} aria-expanded={open}>خيارات التنظيف</Button>
        </div>
      </div>
      {open ? <CleaningPanel orgId={orgId} ds={ds} onApplied={onApplied} /> : null}
    </div>
  )
}
