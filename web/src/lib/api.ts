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
}

export function messageFor(error: unknown): string {
  if (error instanceof ApiError) return MESSAGES[error.code] ?? "حدث خطأ غير متوقع. حاول مجدداً."
  return "حدث خطأ غير متوقع. حاول مجدداً."
}
