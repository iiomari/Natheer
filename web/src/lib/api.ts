/**
 * Browser client for the Nazeer API.
 *
 * Same origin only: the browser calls /api/* on the web origin and Next.js rewrites it to the
 * FastAPI backend, so the session cookie is first-party (host-only, HttpOnly, Secure).
 * Unsafe methods echo the readable CSRF cookie in the X-CSRF-Token header (double submit).
 */

export class ApiError extends Error {
  constructor(
    public status: number,
    public code: string,
    public fields: string[] = [],
  ) {
    super(code)
  }
}

const UNSAFE = new Set(["POST", "PUT", "PATCH", "DELETE"])

function csrfToken(): string | null {
  const m = document.cookie.match(/(?:^|;\s*)(?:__Host-)?nz_csrf=([^;]+)/)
  return m ? decodeURIComponent(m[1]) : null
}

async function refreshCsrf(): Promise<void> {
  await fetch("/api/auth/csrf", { credentials: "same-origin", cache: "no-store" })
}

type Options = { method?: string; body?: unknown; signal?: AbortSignal }

export async function api<T = unknown>(path: string, { method = "GET", body, signal }: Options = {}): Promise<T> {
  const unsafe = UNSAFE.has(method)
  if (unsafe && !csrfToken()) await refreshCsrf()

  const send = () =>
    fetch(`/api${path}`, {
      method,
      signal,
      credentials: "same-origin",
      cache: "no-store",
      headers: {
        ...(body !== undefined ? { "Content-Type": "application/json" } : {}),
        ...(unsafe ? { "X-CSRF-Token": csrfToken() ?? "" } : {}),
      },
      body: body !== undefined ? JSON.stringify(body) : undefined,
    })

  let res: Response
  try {
    res = await send()
    if (unsafe && res.status === 403) {
      const probe = await res.clone().json().catch(() => ({}))
      if (probe?.code === "csrf_failed") {
        await refreshCsrf()
        res = await send()
      }
    }
  } catch (e) {
    if ((e as Error)?.name === "AbortError") throw e
    throw new ApiError(0, "network")
  }
  if (!res.ok) {
    const j = await res.json().catch(() => ({}))
    throw new ApiError(res.status, j?.code ?? "error", j?.fields ?? [])
  }
  if (res.status === 204) return undefined as T
  return (await res.json()) as T
}

/** multipart upload (same CSRF rule as api()). */
export async function upload<T = unknown>(path: string, form: FormData): Promise<T> {
  if (!csrfToken()) await refreshCsrf()
  let res: Response
  try {
    res = await fetch(`/api${path}`, {
      method: "POST",
      credentials: "same-origin",
      headers: { "X-CSRF-Token": csrfToken() ?? "" },
      body: form,
    })
  } catch {
    throw new ApiError(0, "network")
  }
  if (!res.ok) {
    const j = await res.json().catch(() => ({}))
    throw new ApiError(res.status, j?.code ?? (res.status === 413 ? "ingest:total_too_large" : "error"), j?.fields ?? [])
  }
  return (await res.json()) as T
}

/** Arabic, plain, never echoing what the user typed. */
const MESSAGES: Record<string, string> = {
  invalid_credentials: "البريد الإلكتروني أو كلمة المرور غير صحيحة.",
  email_taken: "هذا البريد مسجَّل مسبقاً. سجّل الدخول، أو استعد كلمة المرور.",
  weak_password: "كلمة المرور يجب أن تكون 10 أحرف على الأقل.",
  invalid_email: "صيغة البريد الإلكتروني غير صحيحة.",
  org_name_required: "اكتب اسم المنشأة.",
  name_and_password_required: "اكتب اسمك وكلمة مرور.",
  rate_limited: "محاولات كثيرة خلال وقت قصير. انتظر قليلاً ثم حاول مجدداً.",
  csrf_failed: "انتهت صلاحية الصفحة. حدّثها ثم حاول مجدداً.",
  origin_not_allowed: "تعذّر قبول الطلب من هذا المصدر.",
  invalid_or_expired_token: "الرابط غير صالح أو انتهت صلاحيته.",
  login_required: "لديك حساب بهذا البريد. سجّل الدخول ثم افتح رابط الدعوة مجدداً.",
  invitation_for_other_email: "هذه الدعوة لبريد آخر. سجّل الخروج ثم افتح الرابط مجدداً.",
  already_member: "هذا الشخص عضو في المنشأة بالفعل.",
  last_admin: "لا يمكن إزالة آخر مدير في المنشأة أو تغيير دوره.",
  admin_only: "هذا الإجراء متاح لمدير المنشأة فقط.",
  data_manager_only: "هذا الإجراء متاح للمدير أو مدير البيانات فقط.",
  not_authenticated: "انتهت الجلسة. سجّل الدخول مجدداً.",
  email_not_verified: "أكّد بريدك الإلكتروني أولاً.",
  not_found: "العنصر غير موجود أو لا تملك صلاحية الوصول إليه.",
  invalid_request: "تحقّق من الحقول المطلوبة.",
  network: "تعذّر الاتصال بالخادم. تحقّق من الاتصال وحاول مجدداً.",
  member_of_other_org: "هذا الحساب عضو في منشأة أخرى أيضاً؛ لا يمكن إعادة تعيين كلمة مروره من هنا.",
  quota_exceeded: "امتلأت مساحة التخزين المخصّصة لمنشأتك. احذف مجموعات بيانات قديمة ثم حاول مجدداً.",
  session_expired: "انتهت جلسة المعالجة وحُذفت البيانات الأصلية. ارفع الملفات مجدداً للمتابعة.",
  processing_failed: "تعذّرت معالجة الملفات بسبب خطأ غير متوقع. جرّب مجدداً أو احفظ الملف بصيغة CSV.",
  invalid_merge_key: "اقتراح الدمج غير صالح. حدّث الصفحة وأعد الاختيار.",
  dataset_not_ready: "ما زالت البيانات قيد المعالجة. انتظر قليلاً.",
  synthetic_too_large: "النظير الاصطناعي متاح في النسخة المستضافة حتى 15,000 صف فقط. استخدم النظير المقنّع لهذه البيانات.",
  synthetic_unsupported: "تعذّر توليد نظير اصطناعي لهذه البيانات. النظير المقنّع متاح دائماً.",
  too_many_rows_hosted: "البيانات أكبر من الحد المسموح في النسخة المستضافة (100,000 صف).",
  twin_not_shareable: "لا يمكن مشاركة نظير نتيجته راسب أو حُجب أو حُذف.",
  no_recipients: "اختر عضواً واحداً على الأقل أو أضف مستلماً خارجياً.",
  unknown_member: "أحد الأعضاء المختارين لم يعد في المنشأة.",
  preview_unavailable: "المعاينة متاحة للنظير المقنّع فقط وأثناء جلسة المعالجة.",
  link_already_used: "هذا الرابط استُخدم من حساب آخر. اطلب رابطاً جديداً من المنشأة.",
  share_expired: "انتهت صلاحية هذه المشاركة.",
  share_revoked: "ألغت المنشأة هذه المشاركة.",
  format_not_allowed: "هذه الصيغة غير متاحة لهذه المشاركة.",
  download_link_expired: "انتهت صلاحية رابط التنزيل. اضغط تنزيل مجدداً.",
  bad_download_link: "رابط التنزيل غير صالح لهذا الحساب.",
  "ingest:no_files": "اختر ملفاً واحداً على الأقل.",
  "ingest:too_many_files": "الحد الأقصى 10 ملفات في المرة الواحدة.",
  "ingest:file_too_large": "حجم الملف أكبر من 15 ميجابايت.",
  "ingest:total_too_large": "مجموع حجم الملفات أكبر من 30 ميجابايت.",
  "ingest:empty_file": "الملف فارغ.",
  "ingest:no_data": "لم نجد بيانات في الملف.",
  "ingest:binary_file": "الملف ليس نصاً قابلاً للقراءة. احفظه بصيغة CSV أو xlsx.",
  "ingest:bad_excel": "تعذّر فتح ملف Excel. تأكّد أنه بصيغة xlsx وغير تالف.",
  "ingest:old_excel": "صيغة Excel القديمة (xls) غير مدعومة. احفظ الملف بصيغة xlsx أو CSV.",
  "ingest:unsupported_type": "نوع الملف غير مدعوم. المدعوم: CSV وTSV وTXT وxlsx.",
  "ingest:too_many_rows": "الجدول أكبر من 200,000 صف.",
  "ingest:too_many_columns": "الجدول أكثر من 200 عمود.",
  "ingest:too_many_tables": "الحد الأقصى 12 جدولاً.",
}

export function messageFor(error: unknown): string {
  if (error instanceof ApiError) return MESSAGES[error.code] ?? "حدث خطأ غير متوقع. حاول مجدداً."
  return "حدث خطأ غير متوقع. حاول مجدداً."
}
