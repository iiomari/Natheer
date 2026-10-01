"use client"

import { useId, useState } from "react"
import { Eye, EyeOff } from "lucide-react"

import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { cn } from "@/lib/utils"

export function Field({
  label,
  hint,
  error,
  children,
  htmlFor,
}: {
  label: string
  hint?: React.ReactNode
  error?: string | null
  children: React.ReactNode
  htmlFor?: string
}) {
  return (
    <div className="space-y-2">
      <Label htmlFor={htmlFor}>{label}</Label>
      {children}
      {error ? (
        <p className="text-sm text-sensitive">{error}</p>
      ) : hint ? (
        <p className="text-sm text-muted-foreground">{hint}</p>
      ) : null}
    </div>
  )
}

export function TextField({
  label,
  hint,
  error,
  className,
  ...props
}: React.ComponentProps<"input"> & { label: string; hint?: React.ReactNode; error?: string | null }) {
  const id = useId()
  return (
    <Field label={label} hint={hint} error={error} htmlFor={id}>
      <Input id={id} aria-invalid={error ? true : undefined} className={className} {...props} />
    </Field>
  )
}

/** Emails are typed left-to-right even on an Arabic page. */
export function EmailField(props: Omit<React.ComponentProps<"input">, "type"> & { label?: string; error?: string | null }) {
  return <TextField type="email" autoComplete="email" dir="ltr" label={props.label ?? "البريد الإلكتروني"} {...props} />
}

export function PasswordField({
  label = "كلمة المرور",
  hint,
  error,
  ...props
}: React.ComponentProps<"input"> & { label?: string; hint?: React.ReactNode; error?: string | null }) {
  const id = useId()
  const [shown, setShown] = useState(false)
  return (
    <Field label={label} hint={hint} error={error} htmlFor={id}>
      <div className="relative">
        <Input id={id} type={shown ? "text" : "password"} dir="ltr" className="pe-11" {...props} />
        <button
          type="button"
          onClick={() => setShown((s) => !s)}
          className="absolute inset-y-0 end-0 grid w-10 place-items-center text-muted-foreground hover:text-foreground"
          aria-label={shown ? "إخفاء كلمة المرور" : "إظهار كلمة المرور"}
        >
          {shown ? <EyeOff className="size-4" /> : <Eye className="size-4" />}
        </button>
      </div>
    </Field>
  )
}

/** A styled native select: predictable, accessible, and RTL-correct. */
export function NativeSelect({ className, children, ...props }: React.ComponentProps<"select">) {
  return (
    <select
      className={cn(
        "h-10 w-full rounded-lg border border-input bg-surface px-3 text-base outline-none focus-visible:border-ring focus-visible:ring-3 focus-visible:ring-ring/40 dark:bg-input/30",
        className,
      )}
      {...props}
    >
      {children}
    </select>
  )
}
