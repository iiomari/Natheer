"use client"

import { createContext, useCallback, useContext, useEffect, useState } from "react"
import { usePathname, useRouter } from "next/navigation"

import { ApiError, api } from "@/lib/api"
import type { Me } from "@/lib/types"

type SessionState = { me: Me | null; loading: boolean; refresh: () => Promise<void>; logout: () => Promise<void> }

const SessionContext = createContext<SessionState | null>(null)

/** Loads /api/auth/me once for the workspace; an expired session sends the user to /login. */
export function SessionProvider({ children }: { children: React.ReactNode }) {
  const [me, setMe] = useState<Me | null>(null)
  const [loading, setLoading] = useState(true)
  const router = useRouter()
  const pathname = usePathname()

  const refresh = useCallback(async () => {
    try {
      setMe(await api<Me>("/auth/me"))
    } catch (e) {
      if (e instanceof ApiError && e.status === 401) {
        router.replace(`/login?next=${encodeURIComponent(pathname)}`)
      }
    } finally {
      setLoading(false)
    }
  }, [router, pathname])

  const logout = useCallback(async () => {
    await api("/auth/logout", { method: "POST" }).catch(() => undefined)
    setMe(null)
    router.replace("/login")
  }, [router])

  useEffect(() => {
    // Load once per workspace mount (state is set after the fetch resolves); pages call
    // refresh() after changing membership state.
    // eslint-disable-next-line react-hooks/set-state-in-effect
    void refresh()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  return <SessionContext.Provider value={{ me, loading, refresh, logout }}>{children}</SessionContext.Provider>
}

export function useSession(): SessionState {
  const ctx = useContext(SessionContext)
  if (!ctx) throw new Error("useSession outside SessionProvider")
  return ctx
}
