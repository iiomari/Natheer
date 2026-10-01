"use client"

import { useCallback, useEffect, useState } from "react"

import { ApiError, api } from "@/lib/api"

/** GET a resource with loading / error / reload. Pass null to skip. */
export function useApi<T>(path: string | null) {
  const [data, setData] = useState<T | null>(null)
  const [error, setError] = useState<ApiError | null>(null)
  const [loading, setLoading] = useState(Boolean(path))

  const load = useCallback(async () => {
    if (!path) return
    setLoading(true)
    setError(null)
    try {
      setData(await api<T>(path))
    } catch (e) {
      setError(e instanceof ApiError ? e : new ApiError(0, "error"))
    } finally {
      setLoading(false)
    }
  }, [path])

  useEffect(() => {
    // Fetch on mount and whenever the path changes.
    // eslint-disable-next-line react-hooks/set-state-in-effect
    void load()
  }, [load])

  return { data, error, loading, reload: load, setData }
}

const DATE = new Intl.DateTimeFormat("ar-SA-u-nu-latn-ca-gregory", { dateStyle: "medium", timeStyle: "short" })
const DAY = new Intl.DateTimeFormat("ar-SA-u-nu-latn-ca-gregory", { dateStyle: "medium" })

/** API times are naive UTC ISO strings. */
export function formatDateTime(iso: string): string {
  return DATE.format(new Date(iso.endsWith("Z") ? iso : `${iso}Z`))
}

export function formatDay(iso: string): string {
  return DAY.format(new Date(iso.endsWith("Z") ? iso : `${iso}Z`))
}
