"use client"

import { useEffect, useRef, useState } from "react"
import { Check, Copy, FileSpreadsheet, UploadCloud, X } from "lucide-react"

import { Num } from "@/components/nz"
import { Button } from "@/components/ui/button"
import type { Mark } from "@/lib/types"
import { cn } from "@/lib/utils"

// ---------------------------------------------------------------- highlighted text

const KIND_LABEL: Record<string, string> = {
  SAUDI_ID: "هوية",
  MOBILE: "جوال",
  IBAN: "آيبان",
  EMAIL: "بريد",
  PERSON_NAME: "اسم",
}

const STATUS_STYLE: Record<string, string> = {
  hit: "bg-sensitive-soft border-sensitive/40 text-foreground",
  review: "bg-review-soft border-review/40 text-foreground",
  rejected: "bg-muted border-border text-muted-foreground line-through decoration-2",
  false_alarm: "bg-muted border-dashed border-muted-foreground/60 text-foreground",
  twin: "bg-twin-soft border-twin/40 text-foreground",
}

const CHIP_STYLE: Record<string, string> = {
  hit: "bg-sensitive text-white",
  review: "bg-review text-white",
  rejected: "bg-muted-foreground text-white",
  false_alarm: "bg-muted-foreground text-white",
  twin: "bg-twin text-white",
}

function markLabel(status: string, kind: string): string {
  if (status === "rejected") return "رُفض"
  if (status === "false_alarm") return "إنذار كاذب"
  if (status === "review") return `للمراجعة · ${KIND_LABEL[kind] ?? kind}`
  return KIND_LABEL[kind] ?? kind
}

const NUMERIC_RUN = /((?:SA|\+)?[0-9٠-٩۰-۹](?:[0-9٠-٩۰-۹ \-.,/]*[0-9٠-٩۰-۹])?%?)/g

/** Plain text with every number isolated left-to-right (so spaced Arabic-digit IDs never flip). */
export function BidiText({ text }: { text: string }) {
  const parts = text.split(NUMERIC_RUN)
  return (
    <>
      {parts.map((p, i) => (i % 2 === 1 ? <Num key={i}>{p}</Num> : <span key={i}>{p}</span>))}
    </>
  )
}

/** Status is never color alone: every highlight carries a text label. */
export function HighlightedText({ text, marks, className }: { text: string; marks: Mark[]; className?: string }) {
  const sorted = [...marks].sort((a, b) => a[0] - b[0])
  const out: React.ReactNode[] = []
  let last = 0
  sorted.forEach(([a, b, status, kind], i) => {
    if (a < last) return
    out.push(<BidiText key={`t${i}`} text={text.slice(last, a)} />)
    const value = text.slice(a, b)
    out.push(
      <mark
        key={`m${i}`}
        className={cn("mx-0.5 inline-flex items-baseline gap-1 rounded-md border-b-2 px-1 py-0.5 whitespace-nowrap", STATUS_STYLE[status] ?? STATUS_STYLE.hit)}
      >
        {kind === "PERSON_NAME" ? value : <Num>{value}</Num>}
        <span className={cn("rounded px-1 text-[0.6875rem] font-bold leading-4", CHIP_STYLE[status] ?? CHIP_STYLE.hit)}>
          {markLabel(status, kind)}
        </span>
      </mark>,
    )
    last = b
  })
  out.push(<BidiText key="tail" text={text.slice(last)} />)
  return <p className={cn("text-[1rem] leading-9", className)}>{out}</p>
}

export function MarkLegend() {
  const items: [string, string][] = [
    ["hit", "هوية"], ["hit", "جوال"], ["hit", "آيبان"], ["hit", "اسم"],
    ["review", "للمراجعة"], ["rejected", "رُفض"], ["false_alarm", "إنذار كاذب"],
  ]
  return (
    <div className="flex flex-wrap items-center gap-2 text-sm text-muted-foreground">
      {items.map(([s, l]) => (
        <span key={l} className={cn("rounded px-1.5 text-xs font-bold leading-5", CHIP_STYLE[s])}>{l}</span>
      ))}
    </div>
  )
}

// ---------------------------------------------------------------- data table

export function DataTable({
  columns,
  rows,
  highlight,
  maxHeight = "28rem",
}: {
  columns: string[]
  rows: (string | null)[][]
  highlight?: (row: number, col: number) => boolean
  maxHeight?: string
}) {
  return (
    <div className="overflow-auto rounded-xl border border-border bg-card shadow-card" style={{ maxHeight }}>
      <table className="w-full border-collapse text-sm">
        <thead className="sticky top-0 z-10 bg-muted">
          <tr>
            {columns.map((c) => (
              <th key={c} className="border-b border-border px-4 py-2.5 text-start font-bold whitespace-nowrap">
                <bdi>{c}</bdi>
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((r, i) => (
            <tr key={i} className="border-b border-border last:border-0">
              {r.map((v, j) => (
                <td
                  key={j}
                  className={cn("max-w-[22rem] truncate px-4 py-2.5 align-top", highlight?.(i, j) && "bg-twin-soft font-semibold")}
                  title={v ?? ""}
                >
                  {v === null || v === "" ? <span className="text-muted-foreground/60">—</span> : <BidiText text={v} />}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

// ---------------------------------------------------------------- file drop zone

export function FileDropzone({ files, onChange, accept }: { files: File[]; onChange: (f: File[]) => void; accept: string }) {
  const input = useRef<HTMLInputElement>(null)
  const [over, setOver] = useState(false)
  const add = (list: FileList | null) => {
    if (!list) return
    const merged = [...files]
    for (const f of Array.from(list)) if (!merged.some((m) => m.name === f.name && m.size === f.size)) merged.push(f)
    onChange(merged)
  }
  return (
    <div className="space-y-3">
      <button
        type="button"
        onClick={() => input.current?.click()}
        onDragOver={(e) => {
          e.preventDefault()
          setOver(true)
        }}
        onDragLeave={() => setOver(false)}
        onDrop={(e) => {
          e.preventDefault()
          setOver(false)
          add(e.dataTransfer.files)
        }}
        className={cn(
          "flex w-full flex-col items-center justify-center gap-2 rounded-xl border-2 border-dashed px-6 py-10 text-center transition-colors",
          over ? "border-primary bg-accent" : "border-border bg-surface hover:bg-muted",
        )}
      >
        <UploadCloud className="size-8 text-primary" aria-hidden="true" />
        <span className="font-bold">اسحب الملفات هنا أو اضغط للاختيار</span>
        <span className="text-sm text-muted-foreground">
          CSV أو TSV أو TXT أو Excel (xlsx) · حتى <Num>15</Num> ميجابايت للملف و<Num>10</Num> ملفات
        </span>
      </button>
      <input ref={input} type="file" multiple accept={accept} className="sr-only" onChange={(e) => add(e.target.files)} />
      {files.length ? (
        <ul className="divide-y divide-border rounded-lg border border-border">
          {files.map((f) => (
            <li key={f.name + f.size} className="flex items-center gap-3 px-3 py-2 text-sm">
              <FileSpreadsheet className="size-4 text-muted-foreground" aria-hidden="true" />
              <bdi className="min-w-0 flex-1 truncate">{f.name}</bdi>
              <Num className="text-muted-foreground">{(f.size / 1024).toFixed(0)} KB</Num>
              <Button
                type="button"
                variant="ghost"
                size="icon-sm"
                aria-label={`إزالة ${f.name}`}
                onClick={() => onChange(files.filter((x) => x !== f))}
              >
                <X />
              </Button>
            </li>
          ))}
        </ul>
      ) : null}
    </div>
  )
}

// ---------------------------------------------------------------- copy link

export function CopyLink({ path, label }: { path: string; label?: string }) {
  const [copied, setCopied] = useState(false)
  const url = typeof window === "undefined" ? path : `${window.location.origin}${path}`
  return (
    <div className="space-y-1.5">
      {label ? <p className="text-sm font-semibold">{label}</p> : null}
      <div className="flex items-center gap-2">
        <input
          readOnly
          value={url}
          dir="ltr"
          onFocus={(e) => e.currentTarget.select()}
          className="h-10 min-w-0 flex-1 rounded-lg border border-input bg-muted px-3 font-mono text-sm"
          aria-label={label ?? "الرابط"}
        />
        <Button
          type="button"
          variant="outline"
          onClick={async () => {
            await navigator.clipboard.writeText(url)
            setCopied(true)
            setTimeout(() => setCopied(false), 2000)
          }}
        >
          {copied ? <Check data-icon="inline-start" /> : <Copy data-icon="inline-start" />}
          {copied ? "نُسخ" : "نسخ"}
        </Button>
      </div>
    </div>
  )
}

// ---------------------------------------------------------------- time

export function useNow(intervalMs = 15000): number {
  const [now, setNow] = useState(() => Date.now())
  useEffect(() => {
    const t = setInterval(() => setNow(Date.now()), intervalMs)
    return () => clearInterval(t)
  }, [intervalMs])
  return now
}

export function minutesLeft(iso: string, now: number): number {
  const t = new Date(iso.endsWith("Z") ? iso : `${iso}Z`).getTime()
  return Math.max(0, Math.ceil((t - now) / 60000))
}
