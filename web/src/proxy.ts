import { NextResponse } from "next/server"
import type { NextRequest } from "next/server"

/**
 * Workspace pages need a session cookie; without one, go to /login first.
 * This is only a navigation convenience: every API call is authorized by the backend.
 */
export function proxy(request: NextRequest) {
  const hasSession = request.cookies.has("__Host-nz_session") || request.cookies.has("nz_session")
  if (!hasSession) {
    const url = request.nextUrl.clone()
    url.pathname = "/login"
    url.search = `?next=${encodeURIComponent(request.nextUrl.pathname)}`
    return NextResponse.redirect(url)
  }
  return NextResponse.next()
}

export const config = {
  matcher: ["/app/:path*"],
}
