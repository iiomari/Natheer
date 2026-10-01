"use client"

import { useRouter, useSearchParams } from "next/navigation"
import { Suspense, useEffect } from "react"

import { Spinner } from "@/components/nz"
import { useSession } from "@/lib/session"

/** Sends each user to the right home: their organization, or their received data. */
function Home() {
  const { me } = useSession()
  const router = useRouter()
  const welcome = useSearchParams().get("welcome")

  useEffect(() => {
    if (!me) return
    const first = me.memberships[0]
    const suffix = welcome ? "?welcome=1" : ""
    router.replace(first ? `/app/o/${first.org_id}/dashboard${suffix}` : `/app/received${suffix}`)
  }, [me, router, welcome])

  return (
    <div className="flex items-center gap-3 py-20 text-muted-foreground">
      <Spinner className="size-4" /> جارٍ التحميل…
    </div>
  )
}

export default function AppHome() {
  return (
    <Suspense>
      <Home />
    </Suspense>
  )
}
