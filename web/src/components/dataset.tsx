"use client"

import { minutesLeft } from "@/components/data"
import { Chip, Num } from "@/components/nz"
import type { Dataset } from "@/lib/types"

export function DatasetStatus({ ds, now }: { ds: Dataset; now: number }) {
  if (ds.status === "processing") return <Chip tone="primary">قيد المعالجة</Chip>
  if (ds.status === "failed") return <Chip tone="sensitive">تعذّرت المعالجة</Chip>
  if (ds.session_open)
    return (
      <Chip tone="review">
        الأصول متاحة · <Num>{minutesLeft(ds.session_expires_at, now)}</Num> د
      </Chip>
    )
  return <Chip tone="neutral">حُذفت الأصول</Chip>
}

export const TAG_LABEL: Record<string, { label: string; tone: "sensitive" | "review" | "primary" | "neutral" }> = {
  DIRECT_ID: { label: "معرّف مباشر", tone: "sensitive" },
  QUASI_ID: { label: "شبه معرّف", tone: "review" },
  SENSITIVE: { label: "حساس", tone: "primary" },
  FREE_TEXT: { label: "نص حر", tone: "primary" },
  NORMAL: { label: "عادي", tone: "neutral" },
}

export const KIND_LABEL: Record<string, string> = {
  SAUDI_ID: "هوية / إقامة",
  MOBILE: "جوال",
  IBAN: "آيبان",
  EMAIL: "بريد",
  PERSON_NAME: "اسم",
}

export const DTYPE_LABEL: Record<string, string> = {
  numeric: "رقمي",
  categorical: "فئوي",
  date: "تاريخ",
  short_text: "نص قصير",
  free_text: "نص حر",
}

export const STAGE_LABEL: Record<string, string> = {
  reading_files: "قراءة الملفات واكتشاف البيانات الشخصية",
  generating: "توليد النظير وفحصه",
  requeued: "إعادة المحاولة",
}
