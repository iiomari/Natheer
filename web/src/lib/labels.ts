/**
 * Every technical name the engine produces (check names, detector reasons, data types) has an Arabic
 * label here, so no English string reaches the screen. Details are rebuilt from numbers, never from
 * the engine's English sentences.
 */

export const KIND_AR: Record<string, string> = {
  SAUDI_ID: "هوية / إقامة",
  MOBILE: "جوال",
  IBAN: "آيبان",
  EMAIL: "بريد إلكتروني",
  PERSON_NAME: "اسم",
}

export const CHECK_LABEL: Record<string, string> = {
  leak_scan: "فحص التسريب",
  residual_identifiers: "فحص البقايا",
  exact_copies: "نسخ مطابقة للأصل",
  human_review: "أعمدة للمراجعة",
  free_text_review: "قيم للمراجعة داخل النصوص",
  free_text_replacement: "الاستبدال داخل النصوص",
  detection_vs_golden: "الكشف مقابل مفتاح الإجابة",
  holdout_split: "فصل بيانات الاختبار قبل التدريب",
  dcr: "البُعد عن بيانات التدريب",
  dcr_per_stratum: "البُعد لكل فئة",
  utility_tstr: "الفائدة للتحليل",
  fidelity: "التشابه الإحصائي",
  synthesizer: "النموذج المولِّد",
}

export function checkName(name: string): string {
  const base = name.split("[")[0]
  return CHECK_LABEL[base] ?? "فحص إضافي"
}

function sumValues(v: unknown): number {
  if (typeof v === "number") return v
  if (v && typeof v === "object") return Object.values(v as Record<string, unknown>).reduce<number>((n, x) => n + sumValues(x), 0)
  return 0
}

function byKind(v: unknown): string {
  if (!v || typeof v !== "object") return ""
  const parts = Object.entries(v as Record<string, number>)
    .filter(([, n]) => typeof n === "number" && n > 0)
    .map(([k, n]) => `${KIND_AR[k] ?? "معرّف"}: ${n.toLocaleString("en")}`)
  return parts.length ? ` (${parts.join("، ")})` : ""
}

export type CheckRow = { name: string; status: string; blocking: boolean; detail: string; value?: unknown; threshold?: unknown }

/** One Arabic sentence per check, from its numbers. */
export function checkDetail(c: CheckRow): string {
  const base = c.name.split("[")[0]
  const n = sumValues(c.value)
  switch (base) {
    case "leak_scan":
      return n ? `وُجد ${n.toLocaleString("en")} معرّف حقيقي في النظير${byKind(c.value)}.` : "لا يوجد أي معرّف حقيقي في النظير."
    case "residual_identifiers":
      return n
        ? `بقي ${n.toLocaleString("en")} معرّف صالح لم يولّده نَظير${byKind(c.value)}: يُعد تسريباً.`
        : "لا يوجد في النظير أي رقم هوية أو جوال أو آيبان صالح لم يولّده نَظير."
    case "exact_copies":
      return n ? `${n.toLocaleString("en")} صفاً في النظير مطابق تماماً لصف أصلي.` : "لا يوجد صف مطابق تماماً لصف أصلي."
    case "human_review": {
      const cols = Array.isArray(c.value) ? c.value.length : 0
      return cols ? `${cols} عمود حدّي لم يراجعه أحد، وعومل كمعرّف احتياطاً.` : "لا أعمدة حدّية بانتظار المراجعة."
    }
    case "free_text_review":
      return n ? `${n.toLocaleString("en")} قيمة لم يتأكد منها الكاشف تُركت كما هي للمراجعة${byKind(c.value)}.` : "لا قيم معلّقة للمراجعة."
    case "free_text_replacement":
      return `استُبدل ${n.toLocaleString("en")} معرّفاً داخل النصوص${byKind(c.value)}.`
    case "detection_vs_golden":
      return "مقارنة الكشف بمفتاح الإجابة لبيانات العرض."
    case "holdout_split":
      return "فُصلت بيانات الاختبار قبل تدريب النموذج، فلم يرها أبداً."
    case "dcr":
    case "dcr_per_stratum":
      return "هل صفوف النظير أقرب لبيانات التدريب منها لبيانات لم يرها النموذج؟"
    case "utility_tstr":
      return typeof c.value === "number" ? `أكبر انخفاض في دقة نموذج تدرّب على النظير: ${(c.value as number).toFixed(4)}.` : "لم يُقس لعدم اختيار عمود هدف."
    case "fidelity":
      return "مدى تشابه توزيعات الأعمدة بين النظير والأصل."
    case "synthesizer":
      return "النموذج الإحصائي الذي ولّد الصفوف."
    default:
      return c.status === "PASS" ? "ناجح." : c.status === "FAIL" ? "لم ينجح." : "معلومة."
  }
}

/** The detector's reason for a column, in Arabic. */
export function reasonAr(reason: string): string {
  let m = reason.match(/^(\d+)% of sampled values validate as (\w+)$/)
  if (m) return `${m[1]}% من العيّنة تجتاز التحقق الرسمي كـ${KIND_AR[m[2]] ?? "معرّف"}`
  m = reason.match(/^borderline: (\d+)% validate as (\w+); please review$/)
  if (m) return `حالة حدّية: ${m[1]}% فقط تجتاز التحقق كـ${KIND_AR[m[2]] ?? "معرّف"}، يُرجى المراجعة`
  m = reason.match(/^no identifier pattern \((\w+)\)$/)
  if (m) return `لا يوجد نمط معرّف (${DTYPE_AR[m[1]] ?? "بيانات"})`
  if (reason.startsWith("long Arabic text")) return "نص حر طويل: فُحص بحثاً عن معرّفات داخله"
  if (reason.startsWith("column name suggests a quasi")) return "اسم العمود يدل على صفة عامة (عمر، مدينة، جنس…)"
  if (reason.startsWith("column name suggests sensitive")) return "اسم العمود يدل على محتوى حساس"
  if (reason === "human override") return "عدّله مراجع بشري"
  return "—"
}

export const DTYPE_AR: Record<string, string> = {
  numeric: "رقمي",
  categorical: "فئوي",
  date: "تاريخ",
  short_text: "نص قصير",
  free_text: "نص حر",
}

export const ENCODING_AR: Record<string, string> = {
  "utf-8": "UTF-8",
  "utf-8-sig": "UTF-8",
  "utf-16": "UTF-16",
  "windows-1256": "ويندوز العربي (1256)",
}

export const DELIMITER_AR: Record<string, string> = { ",": "فاصلة", ";": "فاصلة منقوطة", tab: "مسافة جدولة", "|": "خط عمودي" }

const AR_DIGITS = (n: number | string) => String(n).replace(/[0-9]/g, (d) => "٠١٢٣٤٥٦٧٨٩"[Number(d)])

export type DecisionReason = { code: string; n?: number; k?: number; column?: string }

/** One Arabic line explaining a decision on uncertain values. */
export function reasonLine(r: DecisionReason, phrase: string): string {
  const pct = r.n ? Math.round(((r.k ?? 0) / r.n) * 100) : 0
  const ctx = phrase ? `بعد «${phrase}»` : "في هذا العمود"
  switch (r.code) {
    case "chance":
      return `${AR_DIGITS(pct)}٪ فقط من الأرقام ${ctx} تجتاز خوارزمية الهوية — أرقام مرجعية، تُترك.`
    case "ids":
      return `${AR_DIGITS(pct)}٪ من الأرقام ${ctx} تجتاز خوارزمية الهوية — هويات، تُستبدل.`
    case "mixed":
      return `${AR_DIGITS(pct)}٪ من الأرقام ${ctx} تجتاز الخوارزمية — نسبة لا تحسم.`
    case "too_few":
      return `${AR_DIGITS(r.n ?? 0)} أرقام فقط ${ctx} — أقل من أن تُحسم.`
    case "matches_id_column":
      return `يطابق رقماً في عمود الهوية «${(r.column ?? "").split(".").pop()}».`
    case "matches_reference_column":
      return `يطابق رقماً في عمود «${(r.column ?? "").split(".").pop()}» — رقم مرجعي.`
    case "iban_shape":
      return "صيغة آيبان سعودي كاملة — رقم حساب، يُستبدل."
    default:
      return "لا دليل كافٍ."
  }
}
