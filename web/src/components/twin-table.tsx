"use client"

import { useEffect, useState } from "react"
import { ArrowDown, ArrowUp, ChevronLeft, ChevronRight, Search } from "lucide-react"

import { InlineError, Num, Spinner } from "@/components/nz"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { api, messageFor } from "@/lib/api"
import { cn } from "@/lib/utils"

type Cell = [string | null, "replaced" | "review" | null]
type Page = {
  tables: { name: string; rows: number }[]
  table: string
  columns: string[]
  rows: { n: number; cells: Record<string, Cell> }[]
  total: number
  page: number
  pages: number
  size: number
}

const TOKEN = "رمز_التحقق"
const LTR_RE = /^[\s\d+\-.,:/()٠-٩A-Za-z@_]+$/

function Value({ v }: { v: string | null }) {
  if (v == null || v === "") return <span className="text-muted-foreground/60">—</span>
  return LTR_RE.test(v) ? <bdi dir="ltr" className="ltr-num">{v}</bdi> : <bdi>{v}</bdi>
}

export function TwinLegend() {
  return (
    <div className="flex flex-wrap items-center gap-4 text-sm text-muted-foreground">
      <span className="flex items-center gap-2"><span className="inline-block size-4 rounded bg-twin-soft ring-1 ring-twin/30" /> قيمة استُبدلت ببديل</span>
      <span className="flex items-center gap-2"><span className="inline-block size-4 rounded bg-review-soft ring-1 ring-review/50" /> فيها قيمة تُركت للمراجعة</span>
      <span className="flex items-center gap-2"><span className="inline-block size-4 rounded border border-border bg-card" /> لم تتغيّر</span>
    </div>
  )
}

/** The twin, page by page, from the server (search, sort and pagination are server-side). */
export function TwinTable({ endpoint }: { endpoint: string }) {
  const [table, setTable] = useState<string | null>(null)
  const [page, setPage] = useState(1)
  const [q, setQ] = useState("")
  const [query, setQuery] = useState("")
  const [sort, setSort] = useState<{ col: string; desc: boolean } | null>(null)
  const [data, setData] = useState<Page | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    const t = setTimeout(() => { setQuery(q); setPage(1) }, 350)
    return () => clearTimeout(t)
  }, [q])

  useEffect(() => {
    let alive = true
    const params = new URLSearchParams({ page: String(page), size: "50" })
    if (table) params.set("table", table)
    if (query) params.set("q", query)
    if (sort) { params.set("sort", sort.col); params.set("desc", String(sort.desc)) }
    // eslint-disable-next-line react-hooks/set-state-in-effect
    setLoading(true)
    api<Page>(`${endpoint}?${params}`)
      .then((d) => { if (alive) { setData(d); setError(null) } })
      .catch((e) => alive && setError(messageFor(e)))
      .finally(() => alive && setLoading(false))
    return () => { alive = false }
  }, [endpoint, table, page, query, sort])

  if (error) return <InlineError>{error}</InlineError>
  if (!data) return <div className="flex items-center gap-3 py-10 text-muted-foreground"><Spinner className="size-4" /> جارٍ التحميل…</div>

  function toggleSort(col: string) {
    if (col === TOKEN) return
    setSort((s) => (s?.col === col ? (s.desc ? null : { col, desc: true }) : { col, desc: false }))
    setPage(1)
  }

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-3">
        {data.tables.length > 1 ? (
          <div className="flex flex-wrap gap-1 rounded-lg bg-muted p-1" role="tablist" aria-label="الجداول">
            {data.tables.map((t) => (
              <button key={t.name} role="tab" aria-selected={data.table === t.name}
                onClick={() => { setTable(t.name); setPage(1); setSort(null) }}
                className={cn("h-8 rounded-md px-3 text-sm font-semibold", data.table === t.name ? "bg-card shadow-card" : "text-muted-foreground")}>
                <bdi>{t.name}</bdi> <span className="text-xs text-muted-foreground">(<Num>{t.rows.toLocaleString("en")}</Num>)</span>
              </button>
            ))}
          </div>
        ) : <span />}
        <div className="relative w-full max-w-xs">
          <Search className="pointer-events-none absolute start-3 top-1/2 size-4 -translate-y-1/2 text-muted-foreground" aria-hidden="true" />
          <Input value={q} onChange={(e) => setQ(e.target.value)} placeholder="بحث في الجدول" aria-label="بحث في الجدول" className="ps-9" />
        </div>
      </div>
      <TwinLegend />
      <div className={cn("max-h-[65vh] overflow-auto rounded-xl border border-border bg-card shadow-card", loading && "opacity-70")}>
        <table className="w-full border-collapse text-sm">
          <thead className="sticky top-0 z-10 bg-muted">
            <tr>
              <th className="sticky top-0 border-b border-border px-3 py-2.5 text-start font-bold text-muted-foreground">#</th>
              {data.columns.map((c) => (
                <th key={c} className="border-b border-border px-3 py-2.5 text-start font-bold whitespace-nowrap">
                  <button type="button" onClick={() => toggleSort(c)} disabled={c === TOKEN}
                    className="inline-flex items-center gap-1 disabled:cursor-default" aria-label={`ترتيب حسب ${c}`}>
                    <bdi>{c}</bdi>
                    {sort?.col === c ? (sort.desc ? <ArrowDown className="size-3.5" /> : <ArrowUp className="size-3.5" />) : null}
                  </button>
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {data.rows.map((r) => (
              <tr key={r.n} className="border-b border-border/70 last:border-0">
                <td className="px-3 py-2 text-xs text-muted-foreground"><Num>{r.n}</Num></td>
                {data.columns.map((c) => {
                  const [v, mark] = r.cells[c] ?? [null, null]
                  return (
                    <td key={c}
                      className={cn("max-w-80 truncate px-3 py-2",
                        mark === "replaced" && "bg-twin-soft/70",
                        mark === "review" && "bg-review-soft ring-1 ring-inset ring-review/50",
                        c === TOKEN && "font-mono text-xs text-muted-foreground")}
                      title={mark === "review" ? "قيمة تُركت للمراجعة" : undefined}>
                      {mark === "review" ? <span className="me-1 font-bold text-review" aria-label="للمراجعة">؟</span> : null}
                      <Value v={v} />
                    </td>
                  )
                })}
              </tr>
            ))}
            {!data.rows.length ? (
              <tr><td colSpan={data.columns.length + 1} className="px-3 py-10 text-center text-muted-foreground">لا نتائج.</td></tr>
            ) : null}
          </tbody>
        </table>
      </div>
      <div className="flex flex-wrap items-center justify-between gap-3 text-sm">
        <span className="text-muted-foreground">
          <Num>{data.total.toLocaleString("en")}</Num> صف · صفحة <Num>{data.page}</Num> من <Num>{data.pages}</Num>
        </span>
        <div className="flex items-center gap-2">
          <Button variant="outline" size="sm" disabled={data.page <= 1} onClick={() => setPage(data.page - 1)}>
            <ChevronRight data-icon="inline-start" /> السابقة
          </Button>
          <Button variant="outline" size="sm" disabled={data.page >= data.pages} onClick={() => setPage(data.page + 1)}>
            التالية <ChevronLeft data-icon="inline-end" />
          </Button>
        </div>
      </div>
    </div>
  )
}
